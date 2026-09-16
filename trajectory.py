"""
trajectory.py

A simplified 2D (distance vs. height) flight-path model for a batted
baseball, used to answer "given this exit velocity and launch angle,
does the ball clear a fence at distance D and height H?"

This is NOT a full 3D physics simulation. It ignores spray-angle-
dependent effects (wind, spin axis tilt, Magnus side-force) and models
lift as a simple function of launch angle rather than true backspin
rate. It is deliberately simplified -- see README.md for the full list
of known limitations -- but it is calibrated so that a well-struck
100 mph / 25 degree batted ball carries about 370 feet, matching
publicly reported Statcast averages for that combination.

Model:
    - Standard projectile motion with gravity.
    - Quadratic drag opposing velocity (fixed drag coefficient).
    - A Magnus "lift" force perpendicular to velocity, whose magnitude
      is scaled by an assumed backspin proportional to launch angle
      (more backspin as launch angle increases, tapering off past
      ~35 degrees, similar to real backspin-vs-launch-angle trends).

Units: feet, seconds, mph in -> ft/s internally.
"""

import math

G = 32.174            # ft/s^2, gravitational acceleration
RHO = 0.0023769        # slug/ft^3, sea-level air density (15 C)
BALL_MASS = 0.009125   # slug (~5.125 oz regulation baseball)
BALL_RADIUS = 0.1208   # ft (~1.45 in)
AREA = math.pi * BALL_RADIUS ** 2

# Calibrated coefficients (see tune.py derivation in project notes):
# CD ~ 0.33 gives realistic carry distances across the launch-angle
# range; CL_MAX ~ 0.15 gives ~370 ft carry at 100 mph / 25 deg.
DRAG_COEFFICIENT = 0.33
LIFT_COEFFICIENT_MAX = 0.15
LIFT_TAPER_ANGLE_DEG = 35.0  # backspin effectiveness peaks around here

CONTACT_HEIGHT_FT = 3.0   # approximate bat contact height off the ground
TIME_STEP = 0.005          # seconds, integration step
MAX_FLIGHT_TIME = 12.0     # safety cutoff


def _lift_coefficient(launch_angle_rad: float) -> float:
    """Backspin/lift scales up with launch angle, tapering past ~35 deg."""
    taper_rad = math.radians(LIFT_TAPER_ANGLE_DEG)
    scaled = min(launch_angle_rad, taper_rad) / taper_rad
    return LIFT_COEFFICIENT_MAX * math.sin(scaled * math.pi / 2)


def simulate_trajectory(exit_velo_mph: float, launch_angle_deg: float):
    """
    Simulate the flight path of a batted ball.

    Returns a list of (distance_ft, height_ft) points from contact
    until the ball returns to ground level (height <= 0), plus the
    ground "carry" distance (where height crosses zero).

    Only positive launch angles that would produce a fly ball /
    line drive are meaningful here; very low or negative launch
    angles will return a short/immediate landing.
    """
    if exit_velo_mph <= 0:
        return [(0.0, CONTACT_HEIGHT_FT)], 0.0

    v0 = exit_velo_mph * 1.466667  # mph -> ft/s
    theta = math.radians(launch_angle_deg)
    vx = v0 * math.cos(theta)
    vy = v0 * math.sin(theta)
    cl = _lift_coefficient(theta)

    x, y = 0.0, CONTACT_HEIGHT_FT
    t = 0.0
    points = [(x, y)]

    while t < MAX_FLIGHT_TIME:
        v = math.hypot(vx, vy)
        if v < 1e-6:
            break

        drag_force = 0.5 * RHO * DRAG_COEFFICIENT * AREA * v ** 2
        ax_drag = -drag_force * (vx / v) / BALL_MASS
        ay_drag = -drag_force * (vy / v) / BALL_MASS

        lift_force = 0.5 * RHO * cl * AREA * v ** 2
        # Perpendicular to velocity, rotated to push "up" for forward motion.
        ax_lift = -lift_force * (vy / v) / BALL_MASS
        ay_lift = lift_force * (vx / v) / BALL_MASS

        ax = ax_drag + ax_lift
        ay = ay_drag + ay_lift - G

        vx += ax * TIME_STEP
        vy += ay * TIME_STEP
        x += vx * TIME_STEP
        y += vy * TIME_STEP
        t += TIME_STEP

        points.append((x, y))
        if y <= 0 and t > 0.2:
            break

    # Interpolate the exact ground-landing distance.
    (x1, y1), (x2, y2) = points[-2], points[-1]
    if y2 != y1:
        frac = y1 / (y1 - y2)
        carry_distance = x1 + frac * (x2 - x1)
    else:
        carry_distance = x2

    return points, carry_distance


def height_at_distance(points, target_distance: float):
    """
    Linearly interpolate the ball's height at a given horizontal
    distance from the trajectory point list. Returns None if the
    trajectory never reaches that distance.
    """
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if x1 <= target_distance <= x2:
            if x2 == x1:
                return y1
            frac = (target_distance - x1) / (x2 - x1)
            return y1 + frac * (y2 - y1)
    return None


def would_clear_fence(exit_velo_mph: float, launch_angle_deg: float,
                       fence_distance_ft: float, fence_height_ft: float,
                       points=None) -> bool:
    """
    Determine whether a batted ball with the given exit velocity and
    launch angle would clear a fence at fence_distance_ft with height
    fence_height_ft.

    If `points` (a precomputed trajectory) is passed in, it's reused
    instead of re-simulating -- useful when checking the same batted
    ball against many parks.
    """
    if points is None:
        points, _ = simulate_trajectory(exit_velo_mph, launch_angle_deg)

    height = height_at_distance(points, fence_distance_ft)
    if height is None:
        # Ball landed before reaching the fence distance at all.
        return False
    return height >= fence_height_ft
