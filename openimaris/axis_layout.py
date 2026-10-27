"""Screen-space choices for keeping axis annotations apart."""

import numpy as np


def layout_axis_text(items, measure, gap):
    """Place centred text using its screen-space bounds, in logical pixels.

    Each axis shares the widest tick envelope so short and long numbers stay
    aligned. Titles clear both that envelope and the projected frame.
    """
    placed = [dict(item) for item in items]

    def extent(item, direction):
        angle = np.deg2rad(-item.get("rotation", 0))
        along = np.array((np.cos(angle), np.sin(angle)))
        across = np.array((-along[1], along[0]))
        return float(np.abs((direction @ along, direction @ across)) @ np.asarray(measure(item))) / 2

    for axis in "xyz":
        ticks = [item for item in placed if item["axis"] == axis and item["kind"] == "ticks"]
        if not ticks or "axis_line" not in ticks[0]:
            continue
        start, end = ticks[0]["axis_line"]
        tangent = end - start
        length = np.linalg.norm(tangent)
        if length < 1e-9:
            continue
        tangent /= length
        normal = np.array((-tangent[1], tangent[0]))
        if normal @ (ticks[0]["tick_end"] - ticks[0]["tick_start"]) < 0:
            normal = -normal
        envelope = max(extent(item, normal) for item in ticks)
        for item in ticks:
            item["position"] = item["tick_end"] + normal * (envelope + gap)

        title = next((item for item in placed if item["axis"] == axis and item["kind"] == "labels"), None)
        if title is None:
            continue
        if axis == "z":
            # Follow the Z axis while keeping the text readable after inversion.
            angle = (np.rad2deg(np.arctan2(tangent[1], tangent[0])) + 90) % 180 - 90
            title["rotation"] = -float(angle)
        boundary = max(float(point @ normal) for point in title.get("frame", (start, end)))
        boundary = max(boundary, *(float(item["position"] @ normal) + extent(item, normal) for item in ticks))
        center = (start + end) / 2
        title["position"] = center + normal * (boundary + extent(title, normal) + gap - center @ normal)
    return placed


def choose_z_edge(project, size, z_values, xy_positions):
    """Choose a silhouette edge and tick direction far from the X/Y labels.

    Both outward directions at each silhouette corner are candidates. This
    allows Z to point behind the box while the neighbouring axis points in
    front, instead of placing both sets of labels in the same corner.
    """
    x, y, z = size
    corners = [(0, 0), (x, 0), (0, y), (x, y)]
    midpoints = np.array([project((cx, cy, z / 2)) for cx, cy in corners])
    z_vector = project((0, 0, z)) - project((0, 0, 0))
    normal = np.array((-z_vector[1], z_vector[0]))
    length = np.linalg.norm(normal)
    if length < 1e-9:
        normal = np.array((1.0, 0.0))
    else:
        normal /= length
    sides = midpoints @ normal
    candidates = sorted({int(np.argmin(sides)), int(np.argmax(sides))})
    xy = np.array([project(point) for point in xy_positions])
    offset = max(size) * 0.04
    best_score, best = -np.inf, (0, 0, 0)
    for index in candidates:
        cx, cy = corners[index]
        zx, zy = int(cx != 0), int(cy != 0)
        for direction in (0, 1):
            dx = (-1 if zx == 0 else 1) * offset if direction == 0 else 0
            dy = (-1 if zy == 0 else 1) * offset if direction == 1 else 0
            tick_ratio = 0.012 / 0.04
            ends = np.array([project((cx + dx * tick_ratio, cy + dy * tick_ratio, value)) for value in z_values])
            outward = project((cx + dx, cy + dy, z / 2)) - midpoints[index]
            label_normal = normal if outward @ normal >= 0 else -normal
            # Match PDF placement: move away from Z, not along a slanted tick.
            # Otherwise a candidate can seem clear only because its labels
            # have drifted up/down relative to their values.
            labels = ends + label_normal * abs(float(outward @ label_normal))
            # Maximise the closest pair's separation, not just the distance
            # from the box centre. Rounding prevents flips at symmetric views.
            score = float(np.min(np.linalg.norm(labels[:, None] - xy[None, :], axis=2)))
            score = round(score / max(np.ptp(midpoints, axis=0).max(), 1e-9), 6)
            if score > best_score:
                best_score, best = score, (zx, zy, direction)
    return best
