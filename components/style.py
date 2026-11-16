import streamlit as st


def apply_styles() -> None:
    st.html("""
        <style>
        .st-key-geoterroir-evaluation, .st-key-geoterroir-login, .st-key-geoterroir-footer {
            max-width: 48rem; margin-inline: auto;
        }
        .st-key-geoterroir-admin { max-width: 76rem; margin-inline: auto; }
        .st-key-geoterroir-evaluation [class*="st-key-question-"] {
            background: #fffdfa;
            border-radius: .65rem;
            box-shadow: 0 2px 9px #39212908;
        }
        .st-key-geoterroir-evaluation img {
            border-radius: .8rem;
            border: 1px solid #e6ddd6;
            box-shadow: 0 5px 20px #3921290d;
        }
        .st-key-geoterroir-evaluation [role="radiogroup"] label,
        .st-key-geoterroir-evaluation [role="combobox"],
        .st-key-geoterroir-evaluation button,
        .st-key-geoterroir-login button {
            min-height: 44px;
        }
        .st-key-geoterroir-evaluation [role="radiogroup"] label { margin-bottom: 0; }
        [role="option"], [role="option"] * {
            white-space: normal;
            overflow-wrap: anywhere;
        }
        [role="option"] { min-height: 44px; }
        .st-key-admin_archive button:not(:disabled) { border-color: #762c47; color: #762c47; }
        .geoterroir-score {
            border-left: .2rem solid #762c47;
            border-radius: .32rem;
            background: #f3e8ea;
            padding: .7rem .9rem;
            margin-block: .35rem;
        }
        </style>
    """)
