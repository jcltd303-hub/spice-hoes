package live.fishgame.spiceidentity
import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.widget.TextView
class MainActivity:Activity(){override fun onCreate(b:Bundle?){super.onCreate(b);startService(Intent(this,IdentityService::class.java));setContentView(TextView(this).apply{text="Spice Identity service\n127.0.0.1:8082"})}}
