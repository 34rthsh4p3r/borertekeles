import streamlit as st


def apply_styles() -> None:
    st.html("""
        <style>
        .st-key-geoterroir-evaluation, .st-key-geoterroir-login {
            max-width: 48rem; margin-inline: auto;
        }
        .st-key-geoterroir-admin { max-width: 76rem; margin-inline: auto; }
        .dg-admin-brand {
            display: block;
            padding: 0 0 .5rem;
            border-bottom: 1px solid #e4dadc;
            color: #762c47;
            font-size: 1.15rem;
            font-weight: 700;
            text-decoration: none;
        }
        .st-key-geoterroir-admin h1 {
            padding: 0;
            font-size: clamp(1.65rem, 3vw, 2.3rem);
        }
        .st-key-geoterroir-admin [class*="st-key-dg-card-"] {
            background: #fffdfa;
            border-radius: .75rem;
        }
        .st-key-dg-lot-buttons button { min-height: 44px; }
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
        h3.geoterroir-chart-title {
            margin: 0;
            padding: 0;
            font-size: 1.06rem;
            line-height: 1.25;
        }
        .dg-chart-caption, .dg-chart-empty {
            margin: .15rem 0 0;
            color: #635760;
            font-size: .79rem;
        }
        .dg-chart-empty { margin-top: .7rem; }
        .dg-ranking {
            list-style: none;
            display: grid;
            gap: .4rem;
            padding: 0;
            margin: .65rem 0 0;
        }
        .dg-ranking li {
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(2rem, 1fr) auto;
            align-items: center;
            gap: .45rem;
            font-size: .83rem;
            line-height: 1.25;
        }
        .dg-rank-label { overflow-wrap: anywhere; }
        .dg-ranking strong { min-width: 1.6em; text-align: right; font-variant-numeric: tabular-nums; }
        .dg-rank-track, .dg-rank-track i { display: block; height: .5rem; border-radius: 1rem; }
        .dg-rank-track { background: #eee8eb; }
        .dg-rank-more { margin-top: .55rem; font-size: .8rem; color: #635760; }
        .dg-rank-more summary { cursor: pointer; }
        .geoterroir-ring img {
            width: 6.1rem;
            max-width: 100%;
            height: auto;
            display: block;
            margin: 0 auto .35rem;
        }
        .geoterroir-ring ul { list-style: none; max-width: 17rem; margin: .15rem auto 0; padding: 0; }
        .geoterroir-ring li {
            display: grid;
            grid-template-columns: .55rem minmax(0, 1fr) auto;
            align-items: center;
            gap: .45rem;
            padding: .15rem 0;
            font-size: .83rem;
        }
        .geoterroir-ring li strong { white-space: nowrap; }
        .geoterroir-ring li small { color: #635760; font-weight: 400; }
        .geoterroir-swatch { width: .52rem; height: .52rem; border-radius: 50%; }
        .geoterroir-score {
            border-left: .2rem solid #762c47;
            border-radius: .32rem;
            background: #f3e8ea;
            padding: .7rem .9rem;
            margin-block: .35rem;
        }
        </style>
        <script>
        (() => {
            if (window.geoterroirDropdownObserver) return;
            const selector = '.st-key-geoterroir-evaluation input[role="combobox"][inputmode="none"]';
            const lockDropdowns = () => {
                for (const input of document.querySelectorAll(selector)) {
                    if (!input.readOnly) input.readOnly = true;
                }
            };
            // Streamlit's non-searchable menus still use inputs, so block paste and IME edits as well.
            window.geoterroirDropdownObserver = new MutationObserver(lockDropdowns);
            window.geoterroirDropdownObserver.observe(document.body, {
                childList: true, subtree: true, attributes: true, attributeFilter: ['readonly'],
            });
            lockDropdowns();
        })();
        </script>
    """, unsafe_allow_javascript=True)
