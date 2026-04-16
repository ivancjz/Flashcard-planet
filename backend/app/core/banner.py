"""
Shared HTML helpers for tier-gating UI components.

_upgrade_banner_html  — inline banner shown below truncated content
_progate_html         — blur + overlay for fully gated content
"""
from __future__ import annotations

UPGRADE_URL = "/upgrade"


def _upgrade_banner_html(
    feature_label: str,
    cta_label: str = "Upgrade to Pro",
    hidden_count: int = 0,
) -> str:
    """Inline banner placed below a truncated list to invite upgrade."""
    hidden_line = (
        f'<p class="upgrade-banner__count" style="margin:2px 0 0;font-size:0.85em;opacity:0.85;">'
        f"{hidden_count} more available with Pro</p>"
        if hidden_count > 0
        else ""
    )
    return f"""
<div class="upgrade-banner" data-zh="升级到 Pro 以解锁{feature_label}"
     style="display:flex;align-items:center;justify-content:space-between;
            background:#fefce8;border:1px solid #fde68a;border-radius:8px;
            padding:12px 16px;margin-top:12px;">
  <div class="upgrade-banner__body" style="display:flex;align-items:center;gap:12px;">
    <span class="upgrade-banner__icon" style="font-size:1.4em;">&#128274;</span>
    <div class="upgrade-banner__text">
      <strong>Unlock {feature_label}</strong>
      {hidden_line}
    </div>
  </div>
  <a href="{UPGRADE_URL}"
     class="btn btn--pro btn--sm upgrade-banner__cta"
     style="background:#7c3aed;color:white;text-decoration:none;
            padding:6px 14px;border-radius:6px;font-size:0.875em;white-space:nowrap;">
    {cta_label}
  </a>
</div>"""


def _progate_html(
    cta_label: str,
    blurred_content_html: str,
    feature_label: str = "this Pro feature",
) -> str:
    """Blur + overlay wrapper for fully gated content blocks."""
    return f"""
<div class="progate" data-zh="升级以解锁{feature_label}"
     aria-label="Pro feature: {feature_label}"
     style="position:relative;overflow:hidden;border-radius:8px;">
  <div class="progate__blur" aria-hidden="true"
       style="filter:blur(4px);pointer-events:none;user-select:none;">
    {blurred_content_html}
  </div>
  <div class="progate__overlay"
       style="position:absolute;inset:0;display:flex;flex-direction:column;
              align-items:center;justify-content:center;gap:12px;
              background:rgba(255,255,255,0.55);backdrop-filter:blur(2px);">
    <p class="progate__label"
       style="margin:0;font-weight:600;color:#374151;">Pro feature</p>
    <a href="{UPGRADE_URL}"
       class="btn btn--pro"
       style="background:#7c3aed;color:white;text-decoration:none;
              padding:8px 20px;border-radius:6px;font-size:0.9em;">
      {cta_label}
    </a>
  </div>
</div>"""
