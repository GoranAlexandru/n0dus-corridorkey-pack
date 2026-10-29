"""Checks for the pack's own scripts. Standard library only:

    py -3 -m unittest discover -s tests -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import verify  # noqa: E402


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ckpack_verify_"))
        (self.root / "a").mkdir()
        (self.root / "a" / "one.bin").write_bytes(b"\x00\x01" * 1000)
        (self.root / "two with space.txt").write_text("hello")
        (self.root / "manifest").mkdir()
        verify.write_list(self.root, verify.scan(self.root), self.root / verify.LIST_REL, "test")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_clean_tree_passes_and_list_skips_itself(self):
        r = verify.verify(self.root, self.root / verify.LIST_REL)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["files"], 2)
        self.assertNotIn(verify.LIST_REL, [rel for _, _, rel in verify.read_list(self.root / verify.LIST_REL)])

    def test_one_changed_byte_fails(self):
        p = self.root / "a" / "one.bin"
        b = bytearray(p.read_bytes())
        b[500] ^= 1                      # same size, different content
        p.write_bytes(bytes(b))
        r = verify.verify(self.root, self.root / verify.LIST_REL)
        self.assertFalse(r["ok"])
        self.assertEqual(r["wrong"], ["a/one.bin (content differs)"])

    def test_missing_file_fails(self):
        (self.root / "two with space.txt").unlink()
        r = verify.verify(self.root, self.root / verify.LIST_REL)
        self.assertFalse(r["ok"])
        self.assertEqual(r["missing"], ["two with space.txt"])

    def test_extra_files_are_reported_not_failed(self):
        (self.root / "a" / "__pycache__").mkdir()
        (self.root / "a" / "__pycache__" / "x.pyc").write_bytes(b"x")
        r = verify.verify(self.root, self.root / verify.LIST_REL)
        self.assertTrue(r["ok"])
        self.assertEqual(r["extra_count"], 1)

    def test_cli_exit_codes(self):
        ok = subprocess.run([sys.executable, str(REPO / "scripts" / "verify.py"), str(self.root)], capture_output=True)
        self.assertEqual(ok.returncode, 0, ok.stdout)
        (self.root / "a" / "one.bin").write_bytes(b"tampered")
        bad = subprocess.run([sys.executable, str(REPO / "scripts" / "verify.py"), str(self.root)], capture_output=True)
        self.assertEqual(bad.returncode, 1)


class InsideInstallTests(unittest.TestCase):
    """ck_env.inside_install guards the user's outputs from upgrade/uninstall."""

    def test_inside_and_outside(self):
        sys.path.insert(0, str(REPO / "app"))
        import ck_env
        self.assertTrue(ck_env.inside_install(ck_env.ROOT))
        self.assertTrue(ck_env.inside_install(ck_env.ROOT / "data" / "out"))
        self.assertFalse(ck_env.inside_install(ck_env.ROOT.parent / (ck_env.ROOT.name + "_outputs")))
        self.assertFalse(ck_env.inside_install(Path(tempfile.gettempdir())))


class SourcesTests(unittest.TestCase):
    def test_every_pin_present_and_official(self):
        s = json.loads((REPO / "manifest" / "sources.json").read_text())
        official = ("https://github.com/", "https://huggingface.co/", "https://files.pythonhosted.org/",
                    "https://download.pytorch.org/", "https://download-r2.pytorch.org/","https://storage.googleapis.com/representations4d/",
                    "https://developer.download.nvidia.com/", "https://creativecommons.org/",
                    "https://www.apache.org/")
        items = [s["python"], s["ffmpeg"], s["ffmpeg_source"], *s["licence_docs"], *s["models"], *s["wheels"]]
        for it in items:
            self.assertTrue(it["url"].startswith(official), it["url"])
            self.assertRegex(it["sha256"] or "", r"^[0-9a-f]{64}$", f"unpinned: {it['url']}")
        self.assertRegex(s["corridorkey"]["commit"], r"^[0-9a-f]{40}$")
        self.assertRegex(s["utils3d"]["commit"], r"^[0-9a-f]{40}$")

    def test_lock_matches_sources(self):
        s = json.loads((REPO / "manifest" / "sources.json").read_text())
        lock = [l for l in (REPO / "manifest" / "requirements.lock").read_text().splitlines()
                if l and not l.startswith("#")]
        self.assertEqual(len(lock), len(s["wheels"]))
        for w, line in zip(s["wheels"], lock):
            self.assertEqual(line, f"{w['name']}=={w['version']} --hash=sha256:{w['sha256']}")


@unittest.skipUnless(os.environ.get("CKPACK_STAGE_PY"), "needs CKPACK_STAGE_PY=<stage>\\python\\python.exe (numpy, PIL)")
class TestMediaTests(unittest.TestCase):
    def test_regions_sit_on_screen_and_subject(self):
        out = Path(tempfile.mkdtemp(prefix="ckpack_media_"))
        try:
            subprocess.run([os.environ["CKPACK_STAGE_PY"], "-I", str(REPO / "scripts" / "make_test_media.py"), str(out)],
                           check=True, capture_output=True)
            check = (
                "import json,sys,numpy as np;from PIL import Image;o=sys.argv[1];"
                "r=json.load(open(o+'/regions.json'));a=np.asarray(Image.open(o+'/green_test.png')).astype(float)/255;"
                "x0,y0,x1,y1=r['background'];bg=a[y0:y1,x0:x1].mean((0,1));"
                "x0,y0,x1,y1=r['subject'];fg=a[y0:y1,x0:x1].mean((0,1));"
                "assert bg[1]>0.55 and bg[0]<0.25 and bg[2]<0.35,bg;"   # background box is green screen
                "assert abs(fg[0]-fg[1])<0.1 and fg[1]<0.7,fg;print('ok')")  # subject box is the grey body
            r = subprocess.run([os.environ["CKPACK_STAGE_PY"], "-I", "-c", check, str(out)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
        finally:
            shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
