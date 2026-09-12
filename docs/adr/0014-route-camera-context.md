# 14. Route camera context and explicit zoom

Status: accepted for DT-021 implementation, 2026-09-11.

ADR-0012 retains exact step highlighting. This decision clarifies camera behavior:
opening directions selects the first instruction while fitting the complete route
on that instruction's floor, including its markers. Point-only instructions use
route context instead of an arbitrary close-up around one marker. Intentional
walking-step selection may fit the selected span.

Provide keyboard-accessible Zoom in and Zoom out buttons that change the SVG
viewBox around its center, with finite bounded sizes and legible markers. Existing
Show route on this floor and Show whole floor actions remain explicit camera
resets. Page zoom is separate; do not intercept ordinary page scrolling.

A manual camera must survive same-floor redraws. A floor change or intentional
new fit establishes a frame for that floor. Keep camera state independent of route
selection so zoom does not change the instruction, endpoints or route geometry.
Preserve stale scene and route guards. No backend contract or data changes.

Verification requires real-browser containment checks in screen coordinates for
initial route points, zoom expansion/contraction and deterministic resets, using
the user's AQ303 → AQ3149 case on desktop and mobile. Exact path-coordinate tests
remain necessary but do not alone demonstrate that the path is visible.
