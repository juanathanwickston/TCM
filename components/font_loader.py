"""
Font Loader Component
=====================
Loads custom fonts and global theme CSS into Streamlit.
Call inject_custom_fonts() once at app startup after st.set_page_config().
"""

import streamlit as st
from pathlib import Path
import base64


def _load_font_as_base64(font_path: Path) -> str:
    """Load a font file and return as base64 string."""
    with open(font_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def inject_custom_fonts():
    """
    Inject Geist font and global theme CSS into the Streamlit app.
    Must be called once per page, after st.set_page_config().
    """
    assets_dir = Path(__file__).parent.parent / "assets"
    fonts_dir = assets_dir / "fonts" / "geist"
    
    # Load font files as base64 for embedding
    fonts = {
        "regular": fonts_dir / "Geist-Regular.woff2",
        "medium": fonts_dir / "Geist-Medium.woff2",
        "semibold": fonts_dir / "Geist-SemiBold.woff2",
        "bold": fonts_dir / "Geist-Bold.woff2",
    }
    
    # Build @font-face rules with embedded data
    font_faces = []
    weights = {"regular": 400, "medium": 500, "semibold": 600, "bold": 700}
    
    for name, path in fonts.items():
        if path.exists():
            b64 = _load_font_as_base64(path)
            font_faces.append(f"""
@font-face {{
  font-family: "Geist";
  src: url("data:font/woff2;base64,{b64}") format("woff2");
  font-weight: {weights[name]};
  font-style: normal;
  font-display: swap;
}}
""")
    
    # Load theme CSS
    theme_css = ""
    theme_file = assets_dir / "styles" / "theme.css"
    if theme_file.exists():
        theme_css = theme_file.read_text()
    
    # Combine and inject
    full_css = "\n".join(font_faces) + "\n" + theme_css
    
    st.markdown(f"<style>{full_css}</style>", unsafe_allow_html=True)
