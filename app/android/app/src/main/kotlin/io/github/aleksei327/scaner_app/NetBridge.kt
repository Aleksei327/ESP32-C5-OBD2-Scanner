package io.github.aleksei327.scaner_app

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.wifi.WifiNetworkSpecifier
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.PatternMatcher
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel
import okhttp3.Dns
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.net.Inet4Address
import java.net.InetAddress
import java.util.concurrent.TimeUnit

/**
 * Сеть для приложения.
 *
 * 1. Адаптер раздаёт Wi-Fi без интернета, а интернет у телефона остаётся на мобильных данных
 *    (так и нужно). Но тогда запросы к 192.168.4.1 по умолчанию тоже уходят в мобильную сеть.
 *    bindForHost привязывает процесс к той сети Wi-Fi, в которой лежит адрес адаптера.
 *    Samsung всё равно делает Wi-Fi без интернета сетью по умолчанию для всего телефона, поэтому
 *    joinWifi подключает Wi-Fi адаптера как локальную сеть только этого приложения (Android 10+).
 *
 * 2. Удалённый помощник: мост между адаптером (через Wi-Fi) и посредником на компьютере
 *    (через интернет, wss://…/phone?key=…). Сообщения протокола передаются как есть в обе стороны.
 *    Мобильные данные просим явно: Samsung делает Wi-Fi адаптера сетью по умолчанию и гасит 5G/4G.
 */
class NetBridge(context: Context, messenger: BinaryMessenger, private val keepAwake: (Boolean) -> Unit) {
    private val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
    private val main = Handler(Looper.getMainLooper())
    private var sink: EventChannel.EventSink? = null

    private var adapterWs: WebSocket? = null
    private var relayWs: WebSocket? = null
    private var cellCb: ConnectivityManager.NetworkCallback? = null
    private var wifiCb: ConnectivityManager.NetworkCallback? = null
    @Volatile private var localNet: Network? = null
    private var session = 0
    private var toAdapter = 0
    private var toRelay = 0

    init {
        MethodChannel(messenger, "scaner/net").setMethodCallHandler { call, result ->
            when (call.method) {
                "bindForHost" -> result.success(bindForHost(call.argument<String>("host") ?: ""))
                "joinWifi" -> joinWifi(call.argument<String>("ssid") ?: "", call.argument<String>("pass") ?: "", result)
                "remoteStart" -> {
                    remoteStart(call.argument<String>("adapter") ?: "", call.argument<String>("relay") ?: "")
                    result.success(null)
                }
                "remoteStop" -> {
                    remoteStop("off", null)
                    result.success(null)
                }
                else -> result.notImplemented()
            }
        }
        EventChannel(messenger, "scaner/net/remote").setStreamHandler(object : EventChannel.StreamHandler {
            override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
                sink = events
            }

            override fun onCancel(arguments: Any?) {
                sink = null
            }
        })
    }

    private val ipv4 = Regex("""^\d{1,3}(\.\d{1,3}){3}$""")

    /** Сеть Wi-Fi, в подсети которой лежит адрес (только IPv4-адрес, без DNS). */
    @Suppress("DEPRECATION")
    private fun wifiFor(host: String): Network? {
        if (!ipv4.matches(host)) return null
        val addr = InetAddress.getByName(host)
        if (addr.isLoopbackAddress) return null
        for (n in listOfNotNull(localNet) + cm.allNetworks) {
            val caps = cm.getNetworkCapabilities(n) ?: continue
            if (!caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) continue
            val lp = cm.getLinkProperties(n) ?: continue
            if (lp.routes.any { !it.isDefaultRoute && it.matches(addr) }) return n
        }
        return null
    }

    /**
     * Wi-Fi адаптера через WifiNetworkSpecifier: сеть только для этого приложения, сетью по умолчанию
     * она не становится, и интернет всего телефона остаётся на мобильных данных. Android показывает
     * окно «Подключиться к …?». Имя на «-» — шаблон по началу имени (выбор из списка), иначе точное имя.
     * Ответ true, когда сеть поднялась; false — отказ, не нашлась за 60 с или Android старше 10.
     */
    private fun joinWifi(ssid: String, pass: String, result: MethodChannel.Result) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q || ssid.isEmpty()) {
            result.success(false)
            return
        }
        if (localNet?.let { cm.getNetworkCapabilities(it) } != null) {
            result.success(true)
            return
        }
        wifiCb?.let { try { cm.unregisterNetworkCallback(it) } catch (e: IllegalArgumentException) {} }
        val spec = WifiNetworkSpecifier.Builder()
            .apply {
                if (ssid.endsWith("-")) setSsidPattern(PatternMatcher(ssid, PatternMatcher.PATTERN_PREFIX)) else setSsid(ssid)
                if (pass.isNotEmpty()) setWpa2Passphrase(pass)
            }
            .build()
        val req = NetworkRequest.Builder()
            .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
            .removeCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .setNetworkSpecifier(spec)
            .build()
        var answered = false
        val cb = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                localNet = network
                main.post { if (!answered) { answered = true; result.success(true) } }
            }

            override fun onUnavailable() {
                main.post { if (!answered) { answered = true; result.success(false) } }
            }

            override fun onLost(network: Network) {
                if (network == localNet) localNet = null
            }
        }
        wifiCb = cb
        cm.requestNetwork(req, cb, 60_000)
    }

    private fun bindForHost(host: String): Boolean {
        val n = wifiFor(host)
        cm.bindProcessToNetwork(n)
        return n != null
    }

    private fun emit(state: String, msg: String?) {
        val m = mapOf("state" to state, "msg" to msg, "up" to toRelay, "down" to toAdapter)
        main.post { sink?.success(m) }
    }

    /**
     * Мобильные данные для связи с посредником. Пока запрос не отпущен (remoteStop), Android держит их
     * поднятыми, даже если сетью по умолчанию стал Wi-Fi адаптера. Нет SIM или данные выключены — через 10 с null.
     */
    private fun requestCellular(onReady: (Network?) -> Unit) {
        val req = NetworkRequest.Builder()
            .addTransportType(NetworkCapabilities.TRANSPORT_CELLULAR)
            .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .build()
        var done = false
        val cb = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                main.post { if (!done) { done = true; onReady(network) } }
            }

            override fun onUnavailable() {
                main.post { if (!done) { done = true; onReady(null) } }
            }
        }
        cellCb = cb
        cm.requestNetwork(req, cb, 10_000)
    }

    private fun remoteStart(adapterUrl: String, relayUrl: String) {
        remoteStop(null, null)
        val my = ++session
        toAdapter = 0
        toRelay = 0
        emit("connecting", null)
        main.post { keepAwake(true) }
        requestCellular { cell -> if (my == session) connect(my, adapterUrl, relayUrl, cell) }
    }

    private fun connect(my: Int, adapterUrl: String, relayUrl: String, cell: Network?) {
        val host = try { java.net.URI(adapterUrl).host ?: "" } catch (e: Exception) { "" }
        val wifi = wifiFor(host)
        val inet = cell ?: cm.activeNetwork  // интернет — мобильные данные, без них сеть по умолчанию

        val adapterClient = OkHttpClient.Builder()
            .apply { wifi?.let { socketFactory(it.socketFactory) } }
            .connectTimeout(6, TimeUnit.SECONDS)
            .readTimeout(0, TimeUnit.SECONDS)
            .build()
        val relayClient = OkHttpClient.Builder()
            .apply {
                if (inet != null && inet != wifi) {
                    socketFactory(inet.socketFactory)
                    dns(object : Dns {
                        override fun lookup(hostname: String) = inet.getAllByName(hostname).toList()
                    })
                }
            }
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(0, TimeUnit.SECONDS)
            .pingInterval(20, TimeUnit.SECONDS)
            .build()

        // Сначала адаптер (рядом, быстро), потом посредник
        adapterWs = adapterClient.newWebSocket(Request.Builder().url(adapterUrl).build(), object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                if (my != session) return
                relayWs = relayClient.newWebSocket(Request.Builder().url(relayUrl).build(), object : WebSocketListener() {
                    override fun onOpen(webSocket: WebSocket, response: Response) {
                        if (my != session) return
                        emit("on", null)
                        tick(my)
                    }

                    override fun onMessage(webSocket: WebSocket, text: String) {
                        if (my != session) return
                        toAdapter++
                        adapterWs?.send(text)
                    }

                    override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                        if (my == session) remoteStop("off", "relay: $code $reason")
                    }

                    override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                        if (my == session) remoteStop("error", "relay: ${response?.code ?: ""} ${t.message ?: t}")
                    }
                })
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                if (my != session) return
                toRelay++
                relayWs?.send(text)
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                if (my == session) remoteStop("off", "adapter: $code $reason")
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                if (my == session) remoteStop("error", "adapter: ${t.message ?: t}")
            }
        })
    }

    /** Пока мост работает — раз в 2 с сообщаем счётчики, если они изменились. */
    private fun tick(my: Int, lastUp: Int = -1, lastDown: Int = -1) {
        main.postDelayed({
            if (my != session) return@postDelayed
            if (toRelay != lastUp || toAdapter != lastDown) emit("on", null)
            tick(my, toRelay, toAdapter)
        }, 2000)
    }

    private fun remoteStop(state: String?, msg: String?) {
        session++
        adapterWs?.close(1000, null)
        relayWs?.close(1000, null)
        adapterWs = null
        relayWs = null
        cellCb?.let { try { cm.unregisterNetworkCallback(it) } catch (e: IllegalArgumentException) {} }
        cellCb = null
        main.post { keepAwake(false) }
        if (state != null) emit(state, msg)
    }
}
