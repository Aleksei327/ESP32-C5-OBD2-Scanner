package io.github.aleksei327.scaner_app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import java.util.Locale

/**
 * Пока работает удалённый помощник, приложение держит эту службу с уведомлением.
 * Иначе Android, когда приложение уходит в фон (переключились в Claude), закрывает ему сеть,
 * и мост «адаптер ↔ компьютер» рвётся. Сама служба ничего не делает: мост живёт в NetBridge.
 */
class RemoteService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val ru = Locale.getDefault().language == "ru"
        val title = if (ru) "Удалённый помощник подключён" else "Remote assistant connected"
        val text = if (ru) "Компьютер опрашивает машину через этот телефон" else "A computer reads the car through this phone"
        val open = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val builder = if (Build.VERSION.SDK_INT >= 26) {
            getSystemService(NotificationManager::class.java).createNotificationChannel(
                NotificationChannel(CHANNEL, title, NotificationManager.IMPORTANCE_LOW),
            )
            Notification.Builder(this, CHANNEL)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        val n = builder
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setContentTitle(title)
            .setContentText(text)
            .setContentIntent(open)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)
        } else {
            startForeground(1, n)
        }
        return START_NOT_STICKY
    }

    companion object {
        const val CHANNEL = "remote"
    }
}
