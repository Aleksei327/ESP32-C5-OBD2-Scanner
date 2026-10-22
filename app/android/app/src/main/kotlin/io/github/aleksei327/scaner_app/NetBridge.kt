package io.github.aleksei327.scaner_app

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.os.Handler
import android.os.Looper
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
 *
 * 2. Удалённый помощник: мост между адаптером (через Wi-Fi) и посредником на компьютере
 *    (через интернет, wss://…/phone?key=…). Сообщения протокола передаются как есть в обе стороны.
 */
class NetBridge(context: Context, messenger: BinaryMessenger, private val keepAwake: (Boolean) -> Unit) {
    private val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
    private val main = Handler(Looper.getMainLooper())
    private var sink: EventChannel.EventSink? = null

    private var adapterWs: WebSocket? = null
    private var relayWs: WebSocket? = null
    private var session = 0
    private var toAdapter = 0
    private var toRelay = 0

    init {
        MethodChannel(messenger, "scaner/net").setMethodCallHandler { call, result ->
            when (call.method) {
                "bindForHost" -> result.success(bindForHost(call.argument<String>("host") ?: ""))
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
        for (n in cm.allNetworks) {
            val caps = cm.getNetworkCapabilities(n) ?: continue
            if (!caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) continue
            val lp = cm.getLinkProperties(n) ?: continue
            if (lp.routes.any { !it.isDefaultRoute && it.matches(addr) }) return n
        }
        return null
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

    private fun remoteStart(adapterUrl: String, relayUrl: String) {
        remoteStop(null, null)
        val my = ++session
        toAdapter = 0
        toRelay = 0
        emit("connecting", null)
        main.post { keepAwake(true) }

        val host = try { java.net.URI(adapterUrl).host ?: "" } catch (e: Exception) { "" }
        val wifi = wifiFor(host)
        val inet = cm.activeNetwork  // интернет — сеть по умолчанию (мобильные данные), а не привязка процесса

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
        main.post { keepAwake(false) }
        if (state != null) emit(state, msg)
    }
}
