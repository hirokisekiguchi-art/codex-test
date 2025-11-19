#@title 実行後 「🎉 UIを起動します... Public URLが表示されるまでしばらくお待ちください。」と出ます。その文章の「Running on public URL:」すぐ下のリンクを押すとUI画面へ移ります。細かい部分完璧 依存関係 ダウンロードボタン
# ==============================================================================
# 0. 統合に関する注記
# ==============================================================================
# このスクリプトは、2つの独立したスクリプトを1つに統合したものです。
# 安全性を最優先し、以下の原則に従って変更を加えています。
# 1. 既存機能のロジックは一切変更せず、関数や変数をリネームすることで衝突を回避しています。
#    - ポッドキャスト作成関連: `podcast_` プレフィックス
#    - 動画字幕付け関連: `subtitler_` プレフィックス
# 2. 各機能の実行状況を追跡するため、詳細なログ出力を追加しています。
# 3. エラー発生時の原因究明を容易にするため、主要な処理に例外処理を組み込んでいます。
















# ==============================================================================
# 1. 環境構築 (両スクリプトの要件を統合)
# ==============================================================================
print("--- 1. 統合環境の構築を開始します (初回は数分かかります) ---")
!apt-get update -y -qq








# 両方のスクリプトで必要なパッケージをすべてインストール
print("⏳ 必要なシステムパッケージをインストール中...")
!apt-get install -y -qq ffmpeg mecab mecab-ipadic-utf8 git fontconfig \
fonts-noto-cjk fonts-noto-cjk-extra \
fonts-ipafont-gothic fonts-ipafont-mincho








# フォントキャッシュを強制更新 (重要)
print("⏳ フォントキャッシュを更新中...")
!fc-cache -fv > /dev/null








# 両方のスクリプトで必要なPythonライブラリをすべてインストール
print("⏳ 必要なPythonライブラリをインストール中...")
!pip install -q -U pip wheel
!pip install -q -U gradio stable-ts pillow numpy opencv-python-headless scikit-learn








print("✅ 統合環境の構築が完了しました")
















# ==============================================================================
# 2. 共通および各機能の関数定義
# ==============================================================================
import argparse, json, os, shutil, subprocess, tempfile, textwrap, datetime, sys, re, traceback
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image
import cv2
import gradio as gr

try:
    from google.colab import drive as gdrive  # type: ignore
except ImportError:  # pragma: no cover - Colab固有のモジュール
    gdrive = None








print("--- 2. 関数の定義を開始します ---")








# --- 共通ユーティリティ関数 ---
# (より詳細なエラー出力を持つ動画字幕付けスクリプトのrun_chkを採用)
def run_chk(cmd:list[str], **kw) -> None:
 """コマンドを実行しエラーがあれば詳細なログと例外を投げる"""
 try:
     # Popenを使用して標準出力と標準エラーをリアルタイムでストリーミング
     process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', **kw)
     stdout, stderr = process.communicate()
     if process.returncode != 0:
         raise subprocess.CalledProcessError(process.returncode, cmd, output=stdout, stderr=stderr)
 except subprocess.CalledProcessError as e:
     print("--- SUBPROCESS FAILED ---", file=sys.stderr)
     print(f"COMMAND: {' '.join(map(str, e.cmd))}", file=sys.stderr)
     print(f"RETURN CODE: {e.returncode}", file=sys.stderr)
     print("--- STDOUT ---", file=sys.stderr)
     print(e.stdout, file=sys.stderr)
     print("--- STDERR ---", file=sys.stderr)
     print(e.stderr, file=sys.stderr)
     print("-------------------------", file=sys.stderr)
     raise e








def tc(sec: float) -> str:
 """秒数をASS形式のタイムコードに変換"""
 h, m = divmod(int(sec), 3600); m, s = divmod(m, 60)
 return f"{h:01d}:{m:02d}:{s:02d}.{int((sec-int(sec))*100):02d}"








def rgba_string_to_hex(rgba_str):
 """ 'rgba(r, g, b, a)' 形式の文字列を '#RRGGBB' に変換する """
 try:
     parts = re.findall(r"[\d\.]+", rgba_str)
     r, g, b = [int(float(p)) for p in parts[:3]]
     return f"#{r:02x}{g:02x}{b:02x}".upper()
 except:
     return "#FFFFFF"








def hex_to_ass(hex_color: str, alpha_percent: float = 0.0) -> str:
 """WEB形式の色(#RRGGBB)と不透明度(0-100%)を、ASS形式(&HAABBGGRR)に変換"""
 if hex_color and hex_color.strip().startswith('rgba'):
     hex_color = rgba_string_to_hex(hex_color)
 if not hex_color: hex_color = "#FFFFFF"
 hex_color = hex_color.strip().replace("#", "")
 if len(hex_color) != 6: hex_color = "FFFFFF"
 r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
 alpha_val = int((100.0 - float(alpha_percent)) * 2.55)
 alpha_hex = f"{max(0, min(255, alpha_val)):02X}"
 return f"&H{alpha_hex}{b}{g}{r}".upper()








# 利用可能なフォント (両スクリプトで共通)
AVAILABLE_FONTS = ["Noto Sans CJK JP", "Noto Serif CJK JP", "IPAGothic", "IPAMincho"]


PRESET_TYPES = {"podcast", "subtitler"}
DEFAULT_NOTEBOOK_NAME = "MyNotebook"
PRESET_ROOT_NAME = "Subtitle_Presets"
STYLE_FIELD_ORDER = [
    "font", "fs_pct", "txt_col", "txt_alpha",
    "bold", "italic", "underline", "strike",
    "align", "margin_pct", "wrap", "char_spacing",
    "speed",
    "use_out", "out_w", "use_shad", "shad_d", "out_col",
    "use_bg", "bg_col", "bg_alpha"
]

STYLE_VALIDATION_RULES = {
    "font": {"type": str, "choices": AVAILABLE_FONTS},
    "fs_pct": {"type": (int, float), "min": 1, "max": 20},
    "txt_col": {"type": str},
    "txt_alpha": {"type": (int, float), "min": 0, "max": 100},
    "bold": {"type": bool},
    "italic": {"type": bool},
    "underline": {"type": bool},
    "strike": {"type": bool},
    "align": {"type": (int, float), "choices": list(range(1, 10))},
    "margin_pct": {"type": (int, float), "min": 0, "max": 50},
    "wrap": {"type": (int, float), "min": 0, "max": 50},
    "char_spacing": {"type": (int, float), "min": 0, "max": 10},
    "speed": {"type": (int, float), "min": 0.5, "max": 2.0},
    "use_out": {"type": bool},
    "out_w": {"type": (int, float), "min": 0, "max": 10},
    "use_shad": {"type": bool},
    "shad_d": {"type": (int, float), "min": 0, "max": 10},
    "out_col": {"type": str},
    "use_bg": {"type": bool},
    "bg_col": {"type": str},
    "bg_alpha": {"type": (int, float), "min": 0, "max": 100},
}

_drive_mounted = False
_local_drive_fallback = Path("./local_drive").resolve()


def sanitize_notebook_name(name: Optional[str]) -> str:
    """ノートブック名をファイルシステムに安全な形式へ整形"""
    if not name:
        return DEFAULT_NOTEBOOK_NAME
    safe = re.sub(r"[^\w\-一-龠ぁ-んァ-ヶＡ-Ｚａ-ｚ０-９（）() ]+", "_", name.strip())
    safe = safe.strip()
    return safe or DEFAULT_NOTEBOOK_NAME


def sanitize_filename(name: Optional[str]) -> str:
    if not name:
        return "preset"
    safe = re.sub(r"[^\w\-一-龠ぁ-んァ-ヶＡ-Ｚａ-ｚ０-９（）() ]+", "_", name.strip())
    safe = safe.strip("._ ")
    return safe or "preset"


def ensure_drive_mounted() -> Path:
    """Driveがマウントされていなければdrive.mountを呼び出す"""
    global _drive_mounted
    drive_root = Path("/content/drive")
    mydrive = drive_root / "MyDrive"
    if mydrive.exists():
        _drive_mounted = True
        return mydrive
    if gdrive is None:
        _local_drive_fallback.mkdir(parents=True, exist_ok=True)
        return _local_drive_fallback
    if not _drive_mounted:
        print("[INFO] Google Driveをマウントします...")
        gdrive.mount(str(drive_root))
        _drive_mounted = True
    mydrive.mkdir(parents=True, exist_ok=True)
    return mydrive


def get_preset_directory(notebook_name: str, preset_type: str, create: bool = True) -> Path:
    if preset_type not in PRESET_TYPES:
        raise ValueError(f"Unknown preset type: {preset_type}")
    base_dir = ensure_drive_mounted()
    safe_notebook = sanitize_notebook_name(notebook_name)
    preset_dir = base_dir / PRESET_ROOT_NAME / safe_notebook / preset_type
    if create:
        preset_dir.mkdir(parents=True, exist_ok=True)
    return preset_dir


def list_presets(notebook_name: str, preset_type: str) -> List[str]:
    preset_dir = get_preset_directory(notebook_name, preset_type, create=True)
    if not preset_dir.exists():
        return []
    return sorted([p.name for p in preset_dir.glob("*.json")])


def collect_style_settings(values: Tuple[Any, ...]) -> Dict[str, Any]:
    settings = {}
    for key, value in zip(STYLE_FIELD_ORDER, values):
        if isinstance(value, (np.generic,)):
            value = value.item()
        settings[key] = value
    return settings


def _is_valid_color(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    value = value.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return True
    if value.lower().startswith("rgba") or value.lower().startswith("rgb"):
        return True
    return False


def validate_style_settings(settings: Dict[str, Any], preset_type: str) -> Tuple[bool, Optional[str]]:
    if preset_type not in PRESET_TYPES:
        return False, "不明なプリセット種別です。"
    for key in STYLE_FIELD_ORDER:
        if key not in settings:
            return False, f"必須キー {key} が見つかりません。"
        rule = STYLE_VALIDATION_RULES.get(key)
        if not rule:
            continue
        value = settings[key]
        expected_type = rule["type"]
        if expected_type is bool:
            if not isinstance(value, bool):
                return False, f"{key} は真偽値である必要があります。"
        elif not isinstance(value, expected_type):
            return False, f"{key} の値が不正です。"
        if key in {"txt_col", "out_col", "bg_col"}:
            if not _is_valid_color(value):
                return False, f"{key} の色指定が不正です。"
            continue
        if "choices" in rule:
            if value not in rule["choices"]:
                return False, f"{key} の値が許可されていません。"
        if "min" in rule and value < rule["min"]:
            return False, f"{key} の値が下限({rule['min']})を下回っています。"
        if "max" in rule and value > rule["max"]:
            return False, f"{key} の値が上限({rule['max']})を超えています。"
    return True, None


def _write_preset_file(directory: Path, base_name: str, payload: Dict[str, Any]) -> Path:
    safe_base = sanitize_filename(base_name)
    candidate = directory / f"{safe_base}.json"
    counter = 1
    while candidate.exists():
        candidate = directory / f"{safe_base}({counter}).json"
        counter += 1
    with candidate.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return candidate


def save_preset_to_drive(notebook_name: str, preset_name: str, preset_type: str, settings: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
    ok, message = validate_style_settings(settings, preset_type)
    if not ok:
        return False, message or "設定が不正です。", None
    directory = get_preset_directory(notebook_name, preset_type, create=True)
    payload = {
        "type": preset_type,
        "name": preset_name,
        "created_at": datetime.datetime.utcnow().isoformat(),
        "settings": settings,
    }
    saved_path = _write_preset_file(directory, preset_name or preset_type, payload)
    return True, "プリセットを保存しました。", saved_path.name


def load_preset_from_drive(notebook_name: str, filename: str, preset_type: str) -> Dict[str, Any]:
    directory = get_preset_directory(notebook_name, preset_type, create=True)
    preset_path = directory / filename
    if not preset_path.exists():
        raise FileNotFoundError("プリセットファイルが見つかりません。")
    with preset_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if payload.get("type") != preset_type:
        raise ValueError("プリセットの種類が一致しません。")
    settings = payload.get("settings")
    if not isinstance(settings, dict):
        raise ValueError("プリセット設定が不正です。")
    ok, message = validate_style_settings(settings, preset_type)
    if not ok:
        raise ValueError(message or "設定が不正です。")
    return settings


def handle_preset_save(notebook_name: str, preset_name: str, preset_type: str, *values):
    if not notebook_name:
        return gr.Dropdown.update(), "❌ ノートブック名を入力してください。", gr.update(value=preset_name)
    if not preset_name or not preset_name.strip():
        return gr.Dropdown.update(), "❌ プリセット名を入力してください。", gr.update(value=preset_name)
    settings = collect_style_settings(values)
    ok, message, saved_name = save_preset_to_drive(notebook_name, preset_name, preset_type, settings)
    choices = list_presets(notebook_name, preset_type)
    dropdown_update = gr.Dropdown.update(choices=choices, value=saved_name if ok else (choices[0] if choices else None))
    status = f"✅ {message} ({saved_name})" if ok else f"❌ {message}"
    clear_name = "" if ok else preset_name
    return dropdown_update, status, gr.update(value=clear_name)


def handle_preset_refresh(notebook_name: str, preset_type: str):
    choices = list_presets(notebook_name, preset_type)
    default = choices[0] if choices else None
    return gr.Dropdown.update(choices=choices, value=default)


def handle_preset_load(notebook_name: str, filename: str, preset_type: str):
    if not filename:
        raise gr.Error("プリセットが選択されていません。")
    settings = load_preset_from_drive(notebook_name, filename, preset_type)
    values = [settings[key] for key in STYLE_FIELD_ORDER]
    status = f"✅ プリセット『{filename}』を読み込みました。"
    return (*values, status)


def handle_preset_import(uploaded_file, notebook_name: str, preset_type: str):
    if uploaded_file is None:
        choices = list_presets(notebook_name, preset_type)
        default = choices[0] if choices else None
        return gr.Dropdown.update(choices=choices, value=default), "❌ インポートするJSONを選択してください。", uploaded_file
    try:
        with open(uploaded_file.name, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        choices = list_presets(notebook_name, preset_type)
        default = choices[0] if choices else None
        return gr.Dropdown.update(choices=choices, value=default), f"❌ JSONの読み込みに失敗しました: {e}", uploaded_file
    imported_type = payload.get("type")
    if imported_type != preset_type:
        choices = list_presets(notebook_name, preset_type)
        default = choices[0] if choices else None
        return gr.Dropdown.update(choices=choices, value=default), "❌ プリセットの種類が現在のタブと一致しません。", uploaded_file
    settings = payload.get("settings")
    ok, message = validate_style_settings(settings or {}, preset_type)
    if not ok:
        choices = list_presets(notebook_name, preset_type)
        default = choices[0] if choices else None
        return gr.Dropdown.update(choices=choices, value=default), f"❌ インポートに失敗しました: {message}", uploaded_file
    preset_name = payload.get("name") or Path(uploaded_file.name).stem
    _, msg, saved_name = save_preset_to_drive(notebook_name, preset_name, preset_type, settings)
    choices = list_presets(notebook_name, preset_type)
    dropdown_update = gr.Dropdown.update(choices=choices, value=saved_name)
    return dropdown_update, f"✅ {msg} ({saved_name})", None








# ------------------------------------------------------------------------------
# 2-1. ポッドキャスト作成機能の関数 (接頭辞: podcast_)
# ------------------------------------------------------------------------------








def podcast_get_img_size(path:str) -> tuple[int,int]:
 """画像または動画のサイズ(W,H)を取得"""
 try:
    out = subprocess.check_output(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=width,height","-of","csv=p=0", path])
    w, h = map(int, out.decode('utf-8').strip().split(','))
    return w, h
 except: return (1920, 1080)









def podcast_build_ass_text(
    segs, w, h,
    font, fs_pct, txt_col, txt_alpha,
    bold, italic, ul, strike,
    align, margin_pct, wrap, char_spacing,
    use_out, out_w, use_shad, shad_d, out_col,
    use_bg, bg_col, bg_alpha,
    speed=1.0
) -> str:
    """ASSファイルのテキスト内容を生成する (ポッドキャスト用)"""
    fs = int(h * (fs_pct / 100))
    mv = int(h * (margin_pct / 100))
    prim_c = hex_to_ass(txt_col, txt_alpha)
    if use_bg:
        border_style = 3
        out_c_ass = hex_to_ass(bg_col, bg_alpha)
        back_c = "&HFF000000"
    else:
        border_style = 1
        out_c_ass = hex_to_ass(out_col, 100)
        if use_shad:
            back_c = hex_to_ass(out_col, 50)
        else:
            back_c = "&HFF000000"
    bold_f, italic_f = ("-1" if bold else "0"), ("-1" if italic else "0")
    ul_f, strike_f = ("-1" if ul else "0"), ("-1" if strike else "0")
    # [BUGFIX] 座布団(use_bg)が有効な場合、縁取り(use_out)の状態に関わらず、
    # '太さ'(out_w)をASSのOutline値として使用するよう修正。
    if use_bg:
        final_out_w = out_w
        print(f"[DEBUG] podcast_create_ass_content: 座布団が有効なため、'太さ'({out_w})をOutline値として使用します。")
    else:
        final_out_w = out_w if use_out else 0
        print(f"[DEBUG] podcast_create_ass_content: 座布団は無効。縁取り有効({use_out}) -> Outline値は{final_out_w}です。")
    final_shad_d = shad_d if use_shad else 0

    header = textwrap.dedent(f"""
[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: DEF,{font},{fs},{prim_c},{prim_c},{out_c_ass},{back_c},{bold_f},{italic_f},{ul_f},{strike_f},100,100,{char_spacing},0,{border_style},{final_out_w},{final_shad_d},{align},10,10,{mv},1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
""").strip()

    events = ""
    if float(speed) != 1.0:
        print(f"[DEBUG] 字幕タイミングを再生速度 {speed}x に合わせて調整します。")
    for s in segs:
        text = s["text"]
        if wrap > 0 and len(text) > wrap:
            text = r"\N".join(textwrap.wrap(text, int(wrap)))
        start_time = s['start'] / float(speed)
        end_time = s['end'] / float(speed)
        if float(speed) != 1.0:
            print(f"  [DEBUG] ASSタイムコード調整: original=({s['start']:.2f}s, {s['end']:.2f}s) -> adjusted=({start_time:.2f}s, {end_time:.2f}s)")
        events += f"Dialogue: 0,{tc(start_time)},{tc(end_time)},DEF,,0,0,0,,{text}\n"  # MarginVを0に固定
    return header + "\n" + events


def podcast_create_ass_content(*args, **kwargs):
    """Backward compatible wrapper delegating to podcast_build_ass_text."""
    return podcast_build_ass_text(*args, **kwargs)

def podcast_generate_preview(
bg_img, font, fs_pct, txt_col, txt_alpha,
bold, italic, ul, strike,
align, margin_pct, wrap, char_spacing,
use_out, out_w, use_shad, shad_d, out_col,
use_bg, bg_col, bg_alpha
):
 """現在の設定でプレビュー画像を生成する (ポッドキャスト用)"""
 print("--- [DEBUG] ポッドキャスト用プレビュー生成を開始 ---")
 temp_files = []
 try:
     if bg_img and os.path.exists(bg_img):
         bg_path = bg_img
         w, h = podcast_get_img_size(bg_img)
         print(f"[DEBUG] 背景画像を使用: {bg_path} ({w}x{h})")
     else:
         w, h = 1920, 1080
         bg_tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
         bg_path = bg_tmp.name
         bg_tmp.close()
         temp_files.append(bg_path)
         subprocess.run(["ffmpeg","-y","-f","lavfi","-i",f"color=c=black:s={w}x{h}","-frames:v","1",bg_path], check=True, stderr=subprocess.DEVNULL)
         print(f"[DEBUG] デフォルトの黒背景を生成: {bg_path}")








     dummy_segs = [{"start": 0.0, "end": 5.0, "text": "プレビュー用のサンプルテキストです\nここに字幕が表示されます"}]
     ass_content = podcast_create_ass_content(
         dummy_segs, w, h, font, fs_pct, txt_col, txt_alpha,
         bold, italic, ul, strike, align, margin_pct, wrap, char_spacing,
         use_out, out_w, use_shad, shad_d, out_col,
         use_bg, bg_col, bg_alpha
     )
     ass_tmp = tempfile.NamedTemporaryFile(suffix=".ass", delete=False, mode='w', encoding='utf-8')
     ass_tmp.write(ass_content)
     ass_tmp.close()
     temp_files.append(ass_tmp.name)
     print(f"[DEBUG] 一時ASSファイルを作成: {ass_tmp.name}")








     out_png_tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
     out_png = out_png_tmp.name
     out_png_tmp.close()








     safe_ass = ass_tmp.name.replace("\\", "/").replace(":", "\\:")
     cmd = ["ffmpeg", "-y", "-loglevel", "warning", "-i", bg_path, "-vf", f"ass='{safe_ass}'", "-frames:v", "1", out_png]
     print(f"[DEBUG] FFmpegコマンド実行: {' '.join(cmd)}")
     run_chk(cmd)
     print("--- [DEBUG] ポッドキャスト用プレビュー生成に成功 ---")
     return out_png








 except Exception as e:
     print(f"❌ ポッドキャスト用プレビュー生成中にエラーが発生しました。", file=sys.stderr)
     traceback.print_exc()
     return None
 finally:
     for p in temp_files:
         if os.path.exists(p):
             try: os.remove(p)
             except: pass
     print("[DEBUG] 一時ファイルをクリーンアップしました。")








def podcast_generate_speed_preview(audio_file, speed):
   """指定された速度で音声プレビューを生成する"""
   print(f"--- [DEBUG] ポッドキャスト用音声速度プレビュー生成を開始 (速度: {speed}x) ---")
   if not audio_file:
       print("[WARN] 音声ファイルがアップロードされていないため、プレビューをスキップします。")
       return None
  
   temp_audio_out = None
   try:
       temp_audio_out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
      
       # atempoフィルターは0.5から2.0の範囲で動作
       # 範囲外の値はクリップする
       safe_speed = max(0.5, min(2.0, float(speed)))
      
# --- MODIFICATION START ---
       # プレビューは冒頭30秒に限定して高速化
       cmd = [
           "ffmpeg", "-y", "-i", audio_file.name,
           "-af", f"atempo={safe_speed}",
           "-t", "30", # 冒頭30秒のみ処理
           "-loglevel", "error",
           temp_audio_out
       ]
# --- MODIFICATION END ---
      
       print(f"[DEBUG] FFmpeg 音声プレビューコマンド実行: {' '.join(cmd)}")
       run_chk(cmd)
       print("--- [DEBUG] 音声速度プレビュー生成に成功 ---")
       return temp_audio_out
   except Exception as e:
       print(f"❌ 音声速度プレビュー生成中にエラーが発生しました。", file=sys.stderr)
       traceback.print_exc()
       if temp_audio_out and os.path.exists(temp_audio_out):
           os.remove(temp_audio_out)
       return None








def podcast_create_video(
audio, bg_img, script,
font, fs_pct, txt_col, txt_alpha,
bold, italic, ul, strike,
align, margin_pct, wrap, char_spacing,
speed,
use_out, out_w, use_shad, shad_d, out_col,
use_bg, bg_col, bg_alpha
):
 """動画を生成する (ポッドキャスト用)"""
 print("\n--- 📢 ポッドキャスト動画生成処理を開始します ---")
 try:
     if not audio or not script:
         raise gr.Error("必須ファイル（音声、台本）が指定されていません。")


     print(f"[INFO] 再生速度 {speed}x を適用して動画を生成します。")




     run_dir = Path.cwd() / "runs" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S_podcast")
     run_dir.mkdir(parents=True, exist_ok=True)
     print(f"📂 作業ディレクトリを作成しました: {run_dir}")
     mp4_out, ass_out, json_out = str(run_dir/"out.mp4"), str(run_dir/"sub.ass"), str(run_dir/"align.json")








     print("⏳ [1/4] 音声認識を実行中...")
     import stable_whisper
     model = stable_whisper.load_model('small')
     result = model.align(audio, Path(script).read_text(encoding='utf-8'), language='ja')
     result.save_as_json(json_out)
     segs = [s for s in result.to_dict()['segments'] if s['text'].strip()]
     print("✅ [1/4] 音声認識が完了しました。")








     if bg_img:
         w, h, bg_in = *podcast_get_img_size(bg_img), bg_img
     else:
         w, h, bg_in = 1920, 1080, f"color=c=black:s=1920x1080"
     print(f"🖼️ 背景設定: {'画像ファイル' if bg_img else '黒背景'} ({w}x{h})")








     print("⏳ [2/4] 字幕ファイルを作成中...")
     ass_text = podcast_create_ass_content(
         segs, w, h, font, fs_pct, txt_col, txt_alpha,
         bold, italic, ul, strike, align, margin_pct, wrap, char_spacing,
         use_out, out_w, use_shad, shad_d, out_col,
         use_bg, bg_col, bg_alpha,
         speed=speed
     )
     with open(ass_out, "w", encoding="utf-8") as f: f.write(ass_text)
     print("✅ [2/4] 字幕ファイルを作成しました。")








     print("⏳ [3/4] 動画をレンダリング中...")
     input_opts = ["-loop", "1", "-i", bg_in] if bg_img else ["-f", "lavfi", "-i", bg_in]
     # FFmpegコマンドの期間を音声に合わせる
     audio_duration_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio]
     duration_str = subprocess.check_output(audio_duration_cmd).decode('utf-8').strip()








     # lavfiの-iオプションにd={duration}を追加
     if not bg_img:
         # 速度変更を考慮して、元の音声デュレーションを速度で割る
         try:
             original_duration = float(duration_str)
             adjusted_duration = original_duration / float(speed)
             duration_str = str(adjusted_duration)
             print(f"[DEBUG] 速度変更適用後の背景デュレーション: {duration_str}s")
         except ValueError:
             print(f"[WARN] デュレーションの調整に失敗しました。元の値 {duration_str} を使用します。")
         input_opts = ["-f", "lavfi", "-i", f"{bg_in}:d={duration_str}"]


     # 映像と音声に速度変更フィルタを追加
     video_filters = f"setpts=PTS/{speed},ass='{ass_out.replace(':', r'.\:').replace(os.sep, '/')}'"
     audio_filters = f"atempo={speed}"
    
     cmd = ["ffmpeg", "-y"] + input_opts + ["-i", audio, "-vf", video_filters, "-af", audio_filters] + \
           ["-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-b:a", "192k", "-shortest", mp4_out]
     print(f"[DEBUG] FFmpeg Render Command: {' '.join(cmd)}")
     run_chk(cmd)
     print("✅ [3/4] 動画のレンダリングが完了しました。")








     print("🎉 [4/4] 全工程完了！")
     return mp4_out, ass_out, json_out, mp4_out








 except Exception as e:
     print(f"❌ ポッドキャスト動画生成中に致命的なエラーが発生しました。", file=sys.stderr)
     traceback.print_exc()
     # Gradioにエラーメッセージを通知
     raise gr.Error(f"エラーが発生しました: {e}")
















# ------------------------------------------------------------------------------
# 2-2. 動画字幕付け機能の関数 (接頭辞: subtitler_)
# ------------------------------------------------------------------------------








def subtitler_get_video_size(path:str) -> tuple[int,int]:
 """動画のサイズ(W,H)を取得"""
 try:
     out = subprocess.check_output(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=width,height","-of","csv=p=0", path])
     w, h = map(int, out.decode('utf-8').strip().split(','))
     return w, h
 except: return (1920, 1080)








def subtitler_create_ass_content(
segs, w, h,
font, fs_pct, txt_col, txt_alpha,
bold, italic, ul, strike,
align, margin_pct, wrap, char_spacing,
use_out, out_w, use_shad, shad_d, out_col,
use_bg, bg_col, bg_alpha,
speed=1.0
) -> str:
 """ASSファイルのテキスト内容を生成する (動画字幕付け用)"""
 fs = int(h * (fs_pct / 100))
 mv = int(h * (margin_pct / 100))
 prim_c = hex_to_ass(txt_col, txt_alpha)








 if use_bg:
     border_style = 3
     out_c_ass = hex_to_ass(bg_col, bg_alpha)
     back_c = "&HFF000000"
 else:
     border_style = 1
     out_c_ass = hex_to_ass(out_col, 100)
     if use_shad:
         back_c = hex_to_ass(out_col, 50)
     else:
         back_c = "&HFF000000"








 bold_f, italic_f = ("-1" if bold else "0"), ("-1" if italic else "0")
 ul_f, strike_f = ("-1" if ul else "0"), ("-1" if strike else "0")








 if use_bg:
     final_out_w = out_w
 else:
     final_out_w = out_w if use_out else 0
 final_shad_d = shad_d if use_shad else 0








 header = textwrap.dedent(f"""
[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: DEF,{font},{fs},{prim_c},{prim_c},{out_c_ass},{back_c},{bold_f},{italic_f},{ul_f},{strike_f},100,100,{char_spacing},0,{border_style},{final_out_w},{final_shad_d},{align},10,10,{mv},1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
""").strip()








 events = ""
 if float(speed) != 1.0:
   print(f"[DEBUG] 字幕タイミングを再生速度 {speed}x に合わせて調整します。")
 for s in segs:
     text = s["text"].strip().replace("\n", " ")
     if wrap > 0 and len(text) > wrap:
          text = r"\N".join(textwrap.wrap(text, int(wrap)))
     start_time = s['start'] / float(speed)
     end_time = s['end'] / float(speed)
     if float(speed) != 1.0:
         print(f"  [DEBUG] ASSタイムコード調整: original=({s['start']:.2f}s, {s['end']:.2f}s) -> adjusted=({start_time:.2f}s, {end_time:.2f}s)")
     events += f"Dialogue: 0,{tc(start_time)},{tc(end_time)},DEF,,0,0,0,,{text}\n"
 return header + "\n" + events








def subtitler_generate_preview(
video_file, font, fs_pct, txt_col, txt_alpha,
bold, italic, ul, strike,
align, margin_pct, wrap, char_spacing,
use_out, out_w, use_shad, shad_d, out_col,
use_bg, bg_col, bg_alpha
):
 """現在の設定でプレビュー画像を生成する (動画字幕付け用)"""
 print("--- [DEBUG] 動画字幕付け用プレビュー生成を開始 ---")
 temp_files = []
 try:
     bg_tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
     bg_path = bg_tmp.name
     temp_files.append(bg_path)
     if video_file and os.path.exists(video_file):
         w, h = subtitler_get_video_size(video_file)
         cmd_extract = ["ffmpeg","-y","-ss","00:00:01","-i",video_file,"-frames:v","1", "-loglevel", "error", bg_path]
         run_chk(cmd_extract)
         print(f"[DEBUG] 動画ファイルからフレームを抽出: {video_file} ({w}x{h})")
     else:
         w, h = 1920, 1080
         cmd_create_black = ["ffmpeg","-y","-f","lavfi","-i",f"color=c=black:s={w}x{h}","-frames:v","1", "-loglevel", "error", bg_path]
         run_chk(cmd_create_black)
         print(f"[DEBUG] デフォルトの黒背景を生成: {bg_path}")
     bg_tmp.close()








     dummy_segs = [{"start": 0.0, "end": 5.0, "text": "プレビュー用のサンプルテキストです\nここに字幕が表示されます"}]
     ass_content = subtitler_create_ass_content(
         dummy_segs, w, h, font, fs_pct, txt_col, txt_alpha,
         bold, italic, ul, strike, align, margin_pct, wrap, char_spacing,
         use_out, out_w, use_shad, shad_d, out_col,
         use_bg, bg_col, bg_alpha
     )
     ass_tmp = tempfile.NamedTemporaryFile(suffix=".ass", delete=False, mode='w', encoding='utf-8')
     ass_tmp.write(ass_content)
     ass_tmp.close()
     temp_files.append(ass_tmp.name)
     print(f"[DEBUG] 一時ASSファイルを作成: {ass_tmp.name}")








     out_png_tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
     out_png = out_png_tmp.name
     out_png_tmp.close()








     safe_ass_path = ass_tmp.name.replace("\\", "/").replace(":", "\\:")
     vf_option = f"ass='{safe_ass_path}'"
     cmd_burn = ["ffmpeg", "-y", "-i", bg_path, "-vf", vf_option, "-frames:v", "1", "-loglevel", "error", out_png]
     print(f"[DEBUG] FFmpegコマンド実行: {' '.join(cmd_burn)}")
     run_chk(cmd_burn)
     print("--- [DEBUG] 動画字幕付け用プレビュー生成に成功 ---")
     return out_png








 except Exception as e:
     print(f"❌ 動画字幕付け用プレビュー生成中にエラーが発生しました。", file=sys.stderr)
     traceback.print_exc()
     # エラー時も空の画像を返す
     return np.zeros((720, 1280, 3), dtype=np.uint8)
 finally:
     for p in temp_files:
         if os.path.exists(p):
             try: os.remove(p)
             except: pass
     print("[DEBUG] 一時ファイルをクリーンアップしました。")








def subtitler_generate_speed_preview(video_file, speed):
   """動画から音声を抽出し、指定された速度で音声プレビューを生成する"""
   print(f"--- [DEBUG] 動画字幕付け用音声速度プレビュー生成を開始 (速度: {speed}x) ---")
   if not video_file:
       print("[WARN] 動画ファイルがアップロードされていないため、プレビューをスキップします。")
       return None


   temp_audio_in = None
   temp_audio_out = None
   try:
# --- MODIFICATION START ---
       # 1. 動画から音声の冒頭30秒のみを高速に抽出
       print("[DEBUG] プレビューのため、動画の冒頭30秒から音声を抽出します...")
       temp_audio_in = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
       cmd_extract = ["ffmpeg", "-y", "-i", video_file, "-t", "30", "-vn", "-ac", "1", "-ar", "16000", "-loglevel", "error", temp_audio_in]
       print(f"[DEBUG] FFmpeg 音声抽出コマンド実行: {' '.join(cmd_extract)}")
       run_chk(cmd_extract)


       # 2. 抽出した30秒の音声の速度を変更
       temp_audio_out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
       safe_speed = max(0.5, min(2.0, float(speed)))
       cmd_tempo = [
           "ffmpeg", "-y", "-i", temp_audio_in,
           "-af", f"atempo={safe_speed}",
           "-loglevel", "error",
           temp_audio_out
       ]
# --- MODIFICATION END ---
       print(f"[DEBUG] FFmpeg 音声速度変更コマンド実行: {' '.join(cmd_tempo)}")
       run_chk(cmd_tempo)
      
       print("--- [DEBUG] 音声速度プレビュー生成に成功 ---")
       return temp_audio_out
   except Exception as e:
       print(f"❌ 音声速度プレビュー生成中にエラーが発生しました。", file=sys.stderr)
       traceback.print_exc()
       return None
   finally:
       # 一時ファイルをクリーンアップ
       if temp_audio_in and os.path.exists(temp_audio_in):
           os.remove(temp_audio_in)
       # temp_audio_outはGradioが再生後に処理するため、ここでは削除しない
       print("[DEBUG] 一時音声抽出ファイルをクリーンアップしました。")








def subtitler_create_video_with_subs(
video, script,
font, fs_pct, txt_col, txt_alpha,
bold, italic, ul, strike,
align, margin_pct, wrap, char_spacing,
speed,
use_out, out_w, use_shad, shad_d, out_col,
use_bg, bg_col, bg_alpha
):
 """動画に字幕を焼き付ける (動画字幕付け用)"""
 print("\n--- 🎬 動画字幕付け処理を開始します ---")
 try:
     if not video or not script:
         raise gr.Error("必須ファイル（動画、台本）が指定されていません。")
     print(f"[INFO] 再生速度 {speed}x を適用して動画を生成します。")


     run_dir = Path.cwd() / "runs" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S_subtitler")
     run_dir.mkdir(parents=True, exist_ok=True)
     print(f"📂 作業ディレクトリを作成しました: {run_dir}")
     mp4_out, ass_out, json_out = str(run_dir/"final.mp4"), str(run_dir/"sub.ass"), str(run_dir/"align.json")








     print("⏳ [1/4] 動画から音声を抽出中...")
     tmp_audio = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
     cmd_extract = ["ffmpeg","-y","-i",video,"-vn","-ac","1","-ar","16000", "-loglevel", "error", tmp_audio]
     run_chk(cmd_extract)
     print("✅ [1/4] 音声の抽出が完了しました。")








     segs = []
     try:
         print("⏳ [2/4] AIによるアラインメントを実行中...")
         import stable_whisper
         model = stable_whisper.load_model('small')
         result = model.align(tmp_audio, Path(script).read_text(encoding='utf-8'), language='ja')
         result.save_as_json(json_out)
         segs = [s for s in result.to_dict()['segments'] if s['text'].strip()]
         print("✅ [2/4] AIアラインメントが完了しました。")
     finally:
         if os.path.exists(tmp_audio):
             os.remove(tmp_audio)
             print("[DEBUG] 一時音声ファイルを削除しました。")








     print("⏳ [3/4] 字幕ファイルを作成中...")
     w, h = subtitler_get_video_size(video)
     ass_text = subtitler_create_ass_content(
        segs, w, h, font, fs_pct, txt_col, txt_alpha,
        bold, italic, ul, strike, align, margin_pct, wrap, char_spacing,
        use_out, out_w, use_shad, shad_d, out_col,
        use_bg, bg_col, bg_alpha,
        speed=speed
     )
     with open(ass_out, "w", encoding="utf-8") as f: f.write(ass_text)
     print("✅ [3/4] 字幕ファイルを作成しました。")








     print("⏳ [4/4] 動画に字幕をレンダリング中...")
     safe_ass_path_main = ass_out.replace("\\", "/").replace(":", "\\:")
     # fontsdirオプションを追加してColab環境でのフォントパスを明示
     # 速度変更のため、映像と音声にフィルタを適用。音声は再エンコードする。
     video_filters_main = f"setpts=PTS/{speed},ass='{safe_ass_path_main}':fontsdir='/usr/share/fonts/'"
     audio_filters_main = f"atempo={speed}"
     cmd_burn = ["ffmpeg","-y","-i",video,
                 "-vf", video_filters_main,
                 "-af", audio_filters_main,
                 "-c:v","libx264","-preset","ultrafast","-crf","23",
                 "-c:a", "aac", "-b:a", "192k",
                 "-loglevel", "warning", mp4_out]
     print(f"[DEBUG] FFmpeg Render Command: {' '.join(cmd_burn)}")
     run_chk(cmd_burn)
     print("✅ [4/4] 字幕のレンダリングが完了しました。")








     print(f"🎉 全工程完了！ 出力先: {run_dir}")
     return mp4_out, ass_out, json_out








 except Exception as e:
     print(f"❌ 動画字幕付け処理中に致命的なエラーが発生しました。", file=sys.stderr)
     traceback.print_exc()
     raise gr.Error(f"エラーが発生しました: {e}")
















# ==============================================================================
# 3. UI定義 (Gradio)
# ==============================================================================
print("\n--- 3. Gradio UIの定義を開始します ---")








CSS = """
.upload-box { border: 2px dashed #ccc; padding: 20px; text-align: center; background: #f8f9fa; }
#preview-image-podcast, #preview-image-subtitler { min-height: 300px; background: #000; }
#video-result-podcast, #video-result-subtitler { min-height: 400px; background: #000; }
footer { display: none !important; }
"""








with gr.Blocks(theme=gr.themes.Default(), css=CSS, title="字幕作成") as demo:
 gr.Markdown("# 字幕作成")
 gr.Markdown("2つの機能をタブで切り替えて使用できます。※「エフェクト」と「座布団」は共存できません。両方ONにすると座布団が優先されます。")
 notebook_name_input = gr.Textbox(
     label="Google Colab ノートブック名",
     value=DEFAULT_NOTEBOOK_NAME,
     placeholder="例: MySubtitleNotebook",
     info="プリセットはノートブック名ごとに Google Drive 内へ保存されます。"
 )








 with gr.Tabs():
     # ----------------------------------------------------------------------
     # TAB 1: ポッドキャスト作成
     # ----------------------------------------------------------------------
     with gr.TabItem("ポッドキャスト作成"):
         with gr.Row():
             with gr.Column(scale=1):
                 gr.Markdown("### 1. 素材アップロード")
                 podcast_audio_in = gr.File(label="音声 (必須)", elem_classes=["upload-box"])
                 podcast_bg_in = gr.File(label="背景画像 (任意)", elem_classes=["upload-box"])
                 podcast_script_in = gr.File(label="台本.txt (必須)", elem_classes=["upload-box"])








                 gr.Markdown("### 2. 字幕スタイル")
                 podcast_btn_reset_all = gr.Button("すべての設定をデフォルトに戻す", variant="stop")
                 podcast_advanced = gr.Checkbox(label="詳細設定を表示", value=True)
                 with gr.Group(visible=True) as podcast_style_group:
                     with gr.Accordion("基本設定", open=True):
                         podcast_font = gr.Dropdown(AVAILABLE_FONTS, value="Noto Sans CJK JP", label="フォント")
                         podcast_fs = gr.Slider(1, 20, value=7, step=0.5, label="サイズ(%)")
                         podcast_txt_col = gr.ColorPicker("#FFFFFF", label="文字色")
                         podcast_txt_alpha = gr.Slider(0, 100, 100, step=5, label="文字不透明度(%)")
                         podcast_btn_reset_basic = gr.Button("デフォルトに戻す", size="sm")
                     with gr.Accordion("配置・スタイル", open=True):
                         podcast_align = gr.Radio([("左上",7),("上",8),("右上",9),("左",4),("中央",5),("右",6),("左下",1),("下",2),("右下",3)], value=2, label="配置")
                         podcast_margin = gr.Slider(0, 50, 15, step=1, label="垂直マージン(%)")
                         with gr.Row():
                             podcast_b, podcast_i, podcast_u, podcast_s = [gr.Checkbox(label=l, value=v) for l,v in [("太字",True),("斜体",False),("下線",False),("取消線",False)]]
                         podcast_wrap = gr.Slider(0, 50, 20, step=1, label="改行文字数(0=自動OFF)")
                         podcast_char_spacing = gr.Slider(0, 10, value=0, step=0.5, label="文字間隔")
                         with gr.Group():
                             podcast_speed = gr.Slider(0.50, 2.00, value=1.00, step=0.01, label="再生速度")
                             with gr.Row():
                                 podcast_btn_preview_speed = gr.Button("速度を音声でプレビュー")
                                 podcast_audio_preview = gr.Audio(label="音声プレビュー", interactive=False)
                         podcast_btn_reset_style = gr.Button("デフォルトに戻す", size="sm")
                     with gr.Accordion("エフェクト (縁/影)", open=True):
                         with gr.Row():
                             podcast_use_out = gr.Checkbox(label="縁取り", value=True)
                             podcast_out_w = gr.Slider(0, 10, 1.5, step=0.5, label="太さ")
                         with gr.Row():
                             podcast_use_shad = gr.Checkbox(label="影", value=False)
                             podcast_shad_d = gr.Slider(0, 10, 1.0, step=0.5, label="距離")
                         podcast_out_col = gr.ColorPicker("#404040", label="縁/影の色")
                         podcast_btn_reset_effect = gr.Button("デフォルトに戻す", size="sm")
                     with gr.Accordion("背景 (座布団)", open=True):
                         podcast_use_bg = gr.Checkbox(label="座布団を有効化", value=False)
                         podcast_bg_col = gr.ColorPicker("#000000", label="座布団の色")
                         podcast_bg_alpha = gr.Slider(0, 100, 50, step=5, label="座布団の不透明度(%)")
                         podcast_btn_reset_bg = gr.Button("デフォルトに戻す", size="sm")
                     with gr.Accordion("プリセット管理", open=False):
                         podcast_preset_name = gr.Textbox(label="プリセット名", placeholder="例: 配信用テンプレ")
                         with gr.Row():
                             podcast_preset_save_btn = gr.Button("プリセットを保存", variant="primary")
                             podcast_preset_refresh_btn = gr.Button("一覧を更新")
                         podcast_preset_dropdown = gr.Dropdown(label="保存済みプリセット", choices=[], interactive=True)
                         podcast_preset_load_btn = gr.Button("プリセットを読み込み")
                         with gr.Row():
                             podcast_preset_import_file = gr.File(label="プリセットJSONをインポート", file_types=[".json"], file_count="single")
                             podcast_preset_import_btn = gr.Button("インポートして保存")
                         podcast_preset_status = gr.Markdown("")








             with gr.Column(scale=2):
                 gr.Markdown("### 3. プレビュー＆生成")
                 podcast_preview_img = gr.Image(label="リアルタイム・プレビュー", elem_id="preview-image-podcast", interactive=False)
                 with gr.Row():
                     podcast_btn_run = gr.Button("動画を生成開始", variant="primary", scale=2)
                 podcast_vid_out = gr.Video(label="完成動画", elem_id="video-result-podcast")
                 with gr.Accordion("その他生成ファイル", open=False):
                     podcast_files_out = [gr.File(label=l) for l in ["字幕(ASS)","アラインメント(JSON)"]]
                 podcast_mp4_path_state = gr.State(value=None)








     # ----------------------------------------------------------------------
     # TAB 2: 動画字幕付け
     # ----------------------------------------------------------------------
     with gr.TabItem("動画字幕付け"):
         with gr.Row():
             with gr.Column(scale=1):
                 gr.Markdown("### 1. 素材アップロード")
                 subtitler_video_in = gr.Video(label="動画 (必須)", elem_classes=["upload-box"])
                 subtitler_script_in = gr.File(label="台本.txt (必須)", file_types=[".txt"], elem_classes=["upload-box"])








                 gr.Markdown("### 2. 字幕スタイル")
                 subtitler_advanced = gr.Checkbox(label="詳細設定を表示", value=True)
                 with gr.Group(visible=True) as subtitler_style_group:
                     with gr.Accordion("基本設定", open=True):
                         subtitler_font = gr.Dropdown(AVAILABLE_FONTS, value="Noto Sans CJK JP", label="フォント")
                         subtitler_fs = gr.Slider(1, 20, value=7, step=0.5, label="サイズ(%)")
                         subtitler_txt_col = gr.ColorPicker("#FFFFFF", label="文字色")
                         subtitler_txt_alpha = gr.Slider(0, 100, 100, step=5, label="文字不透明度(%)")
                         subtitler_btn_reset_basic = gr.Button("デフォルトに戻す", size="sm")
                     with gr.Accordion("配置・スタイル", open=True):
                         subtitler_align = gr.Radio([("左上",7),("上",8),("右上",9),("左",4),("中央",5),("右",6),("左下",1),("下",2),("右下",3)], value=2, label="配置")
                         subtitler_margin = gr.Slider(0, 50, 15, step=1, label="垂直マージン(%)")
                         with gr.Row():
                             subtitler_b, subtitler_i, subtitler_u, subtitler_s = [gr.Checkbox(label=l, value=v) for l,v in [("太字",True),("斜体",False),("下線",False),("取消線",False)]]
                         subtitler_wrap = gr.Slider(0, 50, 20, step=1, label="改行文字数(0=自動OFF)")
                         subtitler_char_spacing = gr.Slider(0, 10, value=0, step=0.5, label="文字間隔")
                         with gr.Group():
                             subtitler_speed = gr.Slider(0.50, 2.00, value=1.00, step=0.01, label="再生速度")
                             with gr.Row():
                                 subtitler_btn_preview_speed = gr.Button("速度を音声でプレビュー")
                                 subtitler_audio_preview = gr.Audio(label="音声プレビュー", interactive=False)
                         subtitler_btn_reset_style = gr.Button("デフォルトに戻す", size="sm")
                     with gr.Accordion("エフェクト (縁/影)", open=True):
                         with gr.Row():
                             subtitler_use_out = gr.Checkbox(label="縁取り", value=True)
                             subtitler_out_w = gr.Slider(0, 10, 1.5, step=0.5, label="太さ")
                         with gr.Row():
                             subtitler_use_shad = gr.Checkbox(label="影", value=False)
                             subtitler_shad_d = gr.Slider(0, 10, 1.0, step=0.5, label="距離")
                         subtitler_out_col = gr.ColorPicker("#404040", label="縁/影の色")
                         subtitler_btn_reset_effect = gr.Button("デフォルトに戻す", size="sm")
                     with gr.Accordion("背景 (座布団)", open=True):
                         subtitler_use_bg = gr.Checkbox(label="座布団を有効化", value=False)
                         subtitler_bg_col = gr.ColorPicker("#000000", label="座布団の色")
                         subtitler_bg_alpha = gr.Slider(0, 100, 50, step=5, label="座布団の不透明度(%)")
                         subtitler_btn_reset_bg = gr.Button("デフォルトに戻す", size="sm")
                     with gr.Accordion("プリセット管理", open=False):
                         subtitler_preset_name = gr.Textbox(label="プリセット名", placeholder="例: テロップ大")
                         with gr.Row():
                             subtitler_preset_save_btn = gr.Button("プリセットを保存", variant="primary")
                             subtitler_preset_refresh_btn = gr.Button("一覧を更新")
                         subtitler_preset_dropdown = gr.Dropdown(label="保存済みプリセット", choices=[], interactive=True)
                         subtitler_preset_load_btn = gr.Button("プリセットを読み込み")
                         with gr.Row():
                             subtitler_preset_import_file = gr.File(label="プリセットJSONをインポート", file_types=[".json"], file_count="single")
                             subtitler_preset_import_btn = gr.Button("インポートして保存")
                         subtitler_preset_status = gr.Markdown("")








             with gr.Column(scale=2):
                 gr.Markdown("### 3. プレビュー＆生成")
                 subtitler_preview_img = gr.Image(label="リアルタイム・プレビュー", elem_id="preview-image-subtitler", interactive=False)
                 with gr.Row():
                     subtitler_btn_run = gr.Button("動画を生成開始", variant="primary", scale=2)
                 subtitler_vid_out = gr.Video(label="完成動画", elem_id="video-result-subtitler")
                 with gr.Accordion("その他生成ファイル", open=False):
                     subtitler_files_out = [gr.File(label=l) for l in ["字幕(ASS)","アラインメント(JSON)"]]








 # --- イベントリスナー定義 ---
 print("--- 4. UIイベントリスナーを登録します ---")








 # [リスナー] ポッドキャスト作成タブ
 podcast_style_inputs = [
     podcast_bg_in, podcast_font, podcast_fs, podcast_txt_col, podcast_txt_alpha, podcast_b, podcast_i, podcast_u, podcast_s, podcast_align, podcast_margin, podcast_wrap, podcast_char_spacing,
     # speed slider is not for the image preview
     podcast_use_out, podcast_out_w, podcast_use_shad, podcast_shad_d, podcast_out_col, podcast_use_bg, podcast_bg_col, podcast_bg_alpha
 ]
 podcast_style_components_for_presets = [
     podcast_font, podcast_fs, podcast_txt_col, podcast_txt_alpha,
     podcast_b, podcast_i, podcast_u, podcast_s,
     podcast_align, podcast_margin, podcast_wrap, podcast_char_spacing,
     podcast_speed,
     podcast_use_out, podcast_out_w, podcast_use_shad, podcast_shad_d, podcast_out_col,
     podcast_use_bg, podcast_bg_col, podcast_bg_alpha
 ]
 podcast_main_inputs = [
     podcast_audio_in, podcast_bg_in, podcast_script_in,
     podcast_font, podcast_fs, podcast_txt_col, podcast_txt_alpha,
     podcast_b, podcast_i, podcast_u, podcast_s,
     podcast_align, podcast_margin, podcast_wrap, podcast_char_spacing,
     podcast_speed, # new speed input
     podcast_use_out, podcast_out_w, podcast_use_shad, podcast_shad_d, podcast_out_col,
     podcast_use_bg, podcast_bg_col, podcast_bg_alpha
 ]
 for inp in podcast_style_inputs:
     inp.change(fn=podcast_generate_preview, inputs=podcast_style_inputs, outputs=podcast_preview_img)








 podcast_btn_run.click(
     fn=lambda: gr.update(interactive=False, value="生成中..."),
     outputs=[podcast_btn_run]
 ).then(
     fn=podcast_create_video,
     inputs=podcast_main_inputs,
     outputs=[podcast_vid_out, podcast_files_out[0], podcast_files_out[1], podcast_mp4_path_state]
 ).then(
     fn=lambda: gr.update(interactive=True, value="動画を生成開始"),
     outputs=[podcast_btn_run]
 )
 podcast_advanced.change(fn=lambda x: gr.update(visible=x), inputs=podcast_advanced, outputs=podcast_style_group)




 podcast_btn_preview_speed.click(
     fn=podcast_generate_speed_preview,
     inputs=[podcast_audio_in, podcast_speed],
     outputs=podcast_audio_preview
 )




 podcast_btn_reset_basic.click(fn=lambda: ("Noto Sans CJK JP", 7, "#FFFFFF", 100), outputs=[podcast_font, podcast_fs, podcast_txt_col, podcast_txt_alpha])
 podcast_btn_reset_style.click(fn=lambda: (2, 15, True, False, False, False, 20, 0, 1.00), outputs=[podcast_align, podcast_margin, podcast_b, podcast_i, podcast_u, podcast_s, podcast_wrap, podcast_char_spacing, podcast_speed])
 podcast_btn_reset_effect.click(fn=lambda: (True, 1.5, False, 1.0, "#404040"), outputs=[podcast_use_out, podcast_out_w, podcast_use_shad, podcast_shad_d, podcast_out_col])
 podcast_btn_reset_bg.click(fn=lambda: (False, "#000000", 50), outputs=[podcast_use_bg, podcast_bg_col, podcast_bg_alpha])








 podcast_all_style_components = podcast_style_inputs[1:]
 podcast_all_default_values = ("Noto Sans CJK JP", 7, "#FFFFFF", 100, True, False, False, False, 2, 15, 20, 0, True, 1.5, False, 1.0, "#404040", False, "#000000", 50)
 podcast_btn_reset_all.click(
     fn=lambda: ("Noto Sans CJK JP", 7, "#FFFFFF", 100, 2, 15, True, False, False, False, 20, 0, 1.00, True, 1.5, False, 1.0, "#404040", False, "#000000", 50),
     outputs=[
         podcast_font, podcast_fs, podcast_txt_col, podcast_txt_alpha,
         podcast_align, podcast_margin, podcast_b, podcast_i, podcast_u, podcast_s, podcast_wrap, podcast_char_spacing, podcast_speed,
         podcast_use_out, podcast_out_w, podcast_use_shad, podcast_shad_d, podcast_out_col,
         podcast_use_bg, podcast_bg_col, podcast_bg_alpha
     ])

 podcast_preset_save_btn.click(
     fn=lambda notebook_name, preset_name, *values: handle_preset_save(notebook_name, preset_name, "podcast", *values),
     inputs=[notebook_name_input, podcast_preset_name] + podcast_style_components_for_presets,
     outputs=[podcast_preset_dropdown, podcast_preset_status, podcast_preset_name]
 )
 podcast_preset_refresh_btn.click(
     fn=lambda notebook_name: handle_preset_refresh(notebook_name, "podcast"),
     inputs=[notebook_name_input],
     outputs=[podcast_preset_dropdown]
 )
 podcast_preset_load_btn.click(
     fn=lambda notebook_name, filename: handle_preset_load(notebook_name, filename, "podcast"),
     inputs=[notebook_name_input, podcast_preset_dropdown],
     outputs=podcast_style_components_for_presets + [podcast_preset_status]
 )
 podcast_preset_import_btn.click(
     fn=lambda file_obj, notebook_name: handle_preset_import(file_obj, notebook_name, "podcast"),
     inputs=[podcast_preset_import_file, notebook_name_input],
     outputs=[podcast_preset_dropdown, podcast_preset_status, podcast_preset_import_file]
 )












 # [リスナー] 動画字幕付けタブ
 subtitler_style_inputs = [
     subtitler_video_in, subtitler_font, subtitler_fs, subtitler_txt_col, subtitler_txt_alpha, subtitler_b, subtitler_i, subtitler_u, subtitler_s, subtitler_align, subtitler_margin, subtitler_wrap, subtitler_char_spacing,
     subtitler_use_out, subtitler_out_w, subtitler_use_shad, subtitler_shad_d, subtitler_out_col, subtitler_use_bg, subtitler_bg_col, subtitler_bg_alpha
 ]
 subtitler_style_components_for_presets = [
     subtitler_font, subtitler_fs, subtitler_txt_col, subtitler_txt_alpha,
     subtitler_b, subtitler_i, subtitler_u, subtitler_s,
     subtitler_align, subtitler_margin, subtitler_wrap, subtitler_char_spacing,
     subtitler_speed,
     subtitler_use_out, subtitler_out_w, subtitler_use_shad, subtitler_shad_d, subtitler_out_col,
     subtitler_use_bg, subtitler_bg_col, subtitler_bg_alpha
 ]
 subtitler_main_inputs = [
     subtitler_video_in, subtitler_script_in,
     subtitler_font, subtitler_fs, subtitler_txt_col, subtitler_txt_alpha,
     subtitler_b, subtitler_i, subtitler_u, subtitler_s,
     subtitler_align, subtitler_margin, subtitler_wrap, subtitler_char_spacing,
     subtitler_speed, # new speed input
     subtitler_use_out, subtitler_out_w, subtitler_use_shad, subtitler_shad_d, subtitler_out_col,
     subtitler_use_bg, subtitler_bg_col, subtitler_bg_alpha
 ]
 for inp in subtitler_style_inputs:
     inp.change(fn=subtitler_generate_preview, inputs=subtitler_style_inputs, outputs=subtitler_preview_img, show_progress="hidden")








 subtitler_btn_run.click(
    fn=lambda: gr.update(interactive=False, value="生成中..."),
    outputs=[subtitler_btn_run]
 ).then(
    fn=subtitler_create_video_with_subs,
    inputs=subtitler_main_inputs,
    outputs=[subtitler_vid_out, subtitler_files_out[0], subtitler_files_out[1]]
 ).then(
    fn=lambda: gr.update(interactive=True, value="動画を生成開始"),
    outputs=[subtitler_btn_run]
 )
 subtitler_advanced.change(fn=lambda x: gr.update(visible=x), inputs=subtitler_advanced, outputs=subtitler_style_group)




 subtitler_btn_preview_speed.click(
     fn=subtitler_generate_speed_preview,
     inputs=[subtitler_video_in, subtitler_speed],
     outputs=subtitler_audio_preview
 )


 subtitler_btn_reset_basic.click(fn=lambda: ("Noto Sans CJK JP", 7, "#FFFFFF", 100), outputs=[subtitler_font, subtitler_fs, subtitler_txt_col, subtitler_txt_alpha])
 subtitler_btn_reset_style.click(fn=lambda: (2, 15, True, False, False, False, 20, 0, 1.00), outputs=[subtitler_align, subtitler_margin, subtitler_b, subtitler_i, subtitler_u, subtitler_s, subtitler_wrap, subtitler_char_spacing, subtitler_speed])
 subtitler_btn_reset_effect.click(fn=lambda: (True, 1.5, False, 1.0, "#404040"), outputs=[subtitler_use_out, subtitler_out_w, subtitler_use_shad, subtitler_shad_d, subtitler_out_col])
 subtitler_btn_reset_bg.click(fn=lambda: (False, "#000000", 50), outputs=[subtitler_use_bg, subtitler_bg_col, subtitler_bg_alpha])

 subtitler_preset_save_btn.click(
     fn=lambda notebook_name, preset_name, *values: handle_preset_save(notebook_name, preset_name, "subtitler", *values),
     inputs=[notebook_name_input, subtitler_preset_name] + subtitler_style_components_for_presets,
     outputs=[subtitler_preset_dropdown, subtitler_preset_status, subtitler_preset_name]
 )
 subtitler_preset_refresh_btn.click(
     fn=lambda notebook_name: handle_preset_refresh(notebook_name, "subtitler"),
     inputs=[notebook_name_input],
     outputs=[subtitler_preset_dropdown]
 )
 subtitler_preset_load_btn.click(
     fn=lambda notebook_name, filename: handle_preset_load(notebook_name, filename, "subtitler"),
     inputs=[notebook_name_input, subtitler_preset_dropdown],
     outputs=subtitler_style_components_for_presets + [subtitler_preset_status]
 )
 subtitler_preset_import_btn.click(
     fn=lambda file_obj, notebook_name: handle_preset_import(file_obj, notebook_name, "subtitler"),
     inputs=[subtitler_preset_import_file, notebook_name_input],
     outputs=[subtitler_preset_dropdown, subtitler_preset_status, subtitler_preset_import_file]
 )








 # [リスナー] 初期プレビュー生成
demo.load(fn=podcast_generate_preview, inputs=podcast_style_inputs, outputs=podcast_preview_img)
demo.load(fn=subtitler_generate_preview, inputs=subtitler_style_inputs, outputs=subtitler_preview_img)
demo.load(fn=lambda notebook_name: handle_preset_refresh(notebook_name, "podcast"), inputs=[notebook_name_input], outputs=[podcast_preset_dropdown])
demo.load(fn=lambda notebook_name: handle_preset_refresh(notebook_name, "subtitler"), inputs=[notebook_name_input], outputs=[subtitler_preset_dropdown])

notebook_name_input.change(fn=lambda notebook_name: handle_preset_refresh(notebook_name, "podcast"), inputs=[notebook_name_input], outputs=[podcast_preset_dropdown])
notebook_name_input.change(fn=lambda notebook_name: handle_preset_refresh(notebook_name, "subtitler"), inputs=[notebook_name_input], outputs=[subtitler_preset_dropdown])








print("✅ UIの定義とイベント登録が完了しました。")








# ==============================================================================
# 4. UI起動
# ==============================================================================
print("\n🎉 UIを起動します... Public URLが表示されるまでしばらくお待ちください。")
demo.queue()
demo.launch(share=True, debug=True)

