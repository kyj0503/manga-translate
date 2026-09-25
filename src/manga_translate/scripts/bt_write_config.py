"""Runs inside the BallonsTranslator venv (never imported by manga_translate).

Writes <engine>/config/config.json for a headless, text-only run against our local llama-server.
Usage: python bt_write_config.py <engine_root> <base_url> <model_id>
"""
import sys
from pathlib import Path

root = Path(sys.argv[1])
base_url = sys.argv[2].rstrip("/")
model_id = sys.argv[3]
sys.path.insert(0, str(root))

from ballontranslator.utils import shared  # noqa: E402
from ballontranslator.utils.config import pcfg, save_config  # noqa: E402
from ballontranslator.utils.llm_profiles import THINKING_DISABLED, LLMProfile  # noqa: E402

profile = LLMProfile(
    id="manga-translate-llama",
    name="manga-translate llama.cpp",
    base_url=f"{base_url}/v1",
    api_key="sk-no-key-required",
    require_api_key=False,
    model=model_id,
    model_options=[model_id],
    support_text=True,
    support_vision=False,
    support_image=False,
    thinking_level=THINKING_DISABLED,
    max_tokens=2048,
    temperature=0.1,
    top_p=1.0,
    # llama-server constrains the reply to the schema, so every text block gets a translation.
    json_schema_response_format=True,
)

config_path = root / "config" / "config.json"
config_path.parent.mkdir(parents=True, exist_ok=True)
shared.CONFIG_PATH = str(config_path)

m = pcfg.module
m.textdetector = "ctd"
m.ocr = "manga_ocr"
m.inpainter = "lama_large_512px"
m.translator = "LLMTranslator"
m.enable_detect = True
m.enable_ocr = True
m.enable_translate = True
m.enable_inpaint = True
m.llm_profiles = [profile]
m.translator_llm_id = profile.id
m.translate_source = "日本語"
m.translate_target = "한국어"
m.llm_translate_context = "history"
m.llm_translate_vision = False
m.llm_translate_summary_memory = False
pcfg.global_fontformat.font_family = "Malgun Gothic"

ctd = dict(m.textdetector_params.get("ctd") or {})
ctd["mask dilate size"] = 6  # also erase the white outline around the source lettering
ctd["font size multiplier"] = 1.2
ctd["font size min"] = 18
ctd["font size max"] = -1
m.textdetector_params["ctd"] = ctd

if not save_config():
    sys.exit("config save failed")
