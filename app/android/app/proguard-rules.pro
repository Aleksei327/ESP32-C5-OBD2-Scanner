# R8 в релизной сборке выкидывал методы плагина shared_preferences, которые
# вызываются из нативного кода (JNI): приложение падало на старте с NoSuchMethodError
# SharedPreferencesApiRegistrar.getAll. Оставляем плагин целиком.
-keep class io.flutter.plugins.sharedpreferences.** { *; }
# Плагин ходит в Kotlin через JNI (package:jni) и ищет классы корутин по именам
# (список — в исходниках package:jni: Unit, Result, Result$Failure, coroutines.*): их R8 трогать не должен.
-keep class kotlin.coroutines.** { *; }
-keep class kotlin.Unit { *; }
-keep class kotlin.Result { *; }
-keep class kotlin.Result$Failure { *; }
-keep class com.github.dart_lang.jni.** { *; }
