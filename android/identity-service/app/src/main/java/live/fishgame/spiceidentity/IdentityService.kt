package live.fishgame.spiceidentity
import android.app.Service
import android.content.Intent
import android.os.IBinder
import java.net.ServerSocket
import kotlin.concurrent.thread
class IdentityService:Service(){@Volatile private var running=true
 override fun onBind(i:Intent?):IBinder?=null
 override fun onCreate(){super.onCreate();thread(name="spice-identity-http"){ServerSocket(8082,8,java.net.InetAddress.getByName("127.0.0.1")).use{s->while(running){val c=s.accept();c.use{sock->val input=sock.getInputStream().bufferedReader();val line=input.readLine()?:"";while(true){val h=input.readLine();if(h.isNullOrEmpty())break};val body=if(line.startsWith("GET /health ")) """{"ready":true,"backend":"service-shell","accelerated":false,"port":8082}""" else """{"error":"transfer backend not loaded"}""";val status=if(line.startsWith("GET /health ")) "200 OK" else "503 Service Unavailable";sock.getOutputStream().write("HTTP/1.1 $status\r\nContent-Type: application/json\r\nContent-Length: ${body.toByteArray().size}\r\nConnection: close\r\n\r\n$body".toByteArray())}}}}}}
 override fun onDestroy(){running=false;super.onDestroy()}}
