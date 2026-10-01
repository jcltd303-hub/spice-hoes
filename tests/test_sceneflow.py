import base64,json,tempfile,unittest
from pathlib import Path
from spicecore.localdream import encode_image_file
from spicecore.sceneflow import load_reference,scene_prompt
class SceneFlowTests(unittest.TestCase):
 def test_reference_file_is_base64_encoded(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"x.png"; raw=bytes.fromhex("89504e470d0a1a0a")+"x".encode(); p.write_bytes(raw)
   self.assertEqual(base64.b64decode(encode_image_file(p)),raw)
 def test_manifest_load_and_scene_prompt(self):
  with tempfile.TemporaryDirectory() as d:
   d=Path(d); a=d/"ref.png"; a.write_bytes(bytes.fromhex("89504e470d0a1a0a")+"x".encode())
   (d/"celeste_vale.json").write_text(json.dumps({"reference_asset":str(a),"sha256":"abc"}))
   ref,asset=load_reference("celeste_vale",d)
   self.assertEqual(asset,a); self.assertEqual(ref["sha256"],"abc")
   self.assertIn("exact same original fictional adult woman",scene_prompt("hotel-lobby"))
if __name__=="__main__": unittest.main()
