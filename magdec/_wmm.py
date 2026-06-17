"""
Spherical harmonic evaluation of the World Magnetic Model.

Algorithm: direct port of the NOAA WMM Fortran code as distributed by
Christopher Weiss (geomag.py, public domain), restructured for clarity and
multi-epoch support.  The mathematics follow the WMM Technical Note
(Chulliat et al. 2020).
"""

import math
import os
from dataclasses import dataclass
from datetime import date as _date

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# WGS-84 ellipsoid constants (km)
_A = 6378.137
_B = 6356.7523142
_RE = 6371.2          # WMM reference radius
_A2 = _A * _A
_B2 = _B * _B
_C2 = _A2 - _B2
_A4 = _A2 * _A2
_B4 = _B2 * _B2
_C4 = _A4 - _B4


@dataclass
class MagResult:
    """All magnetic field components at a single point."""
    D: float   # declination, degrees east
    I: float   # inclination (dip), degrees (positive = downward)
    H: float   # horizontal intensity, nT
    X: float   # north component, nT
    Y: float   # east component, nT
    Z: float   # vertical component, nT (positive = downward)
    F: float   # total intensity, nT
    model: str
    date: str


class WMM:
    """
    Single-epoch WMM model loaded from a .COF coefficient file.
    Supports any spherical harmonic degree — standard WMM (n≤12) and
    high-resolution variants (e.g. WMMHR, n≤133).

    Parameters
    ----------
    cof_path : str
        Path to a WMM .COF file (e.g. WMM2020.COF, WMMHR.COF).
    """

    def __init__(self, cof_path: str):
        self._load(cof_path)
        sz = self._sz
        self._buf_sp = [0.0] * sz
        self._buf_cp = [0.0] * sz
        self._buf_pp = [0.0] * sz
        self._buf_p = [[0.0] * sz for _ in range(sz)]
        self._buf_dp = [[0.0] * sz for _ in range(sz)]
        self._buf_tc = [[0.0] * sz for _ in range(sz)]

    # ------------------------------------------------------------------
    # coefficient loading
    # ------------------------------------------------------------------

    def _load(self, path: str):
        rows = []
        with open(path) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 3:
                    try:
                        self.epoch = float(parts[0])
                        self.name = parts[1]
                    except ValueError:
                        pass
                elif len(parts) == 6:
                    n = int(parts[0])
                    if n < 900:   # skip terminator lines
                        rows.append((n, int(parts[1]),
                                     float(parts[2]), float(parts[3]),
                                     float(parts[4]), float(parts[5])))

        maxord = max(r[0] for r in rows)
        sz = maxord + 2

        def _z(r, c=None):
            return [[0.0] * (c or sz) for _ in range(r or sz)]

        coef = _z(sz)
        dcoef = _z(sz)

        # g(n,m)  stored at coef[m][n]   (lower triangle, m ≤ n)
        # h(n,m)  stored at coef[n][m-1] (upper triangle, repurposed row n, col m-1)
        # Same scheme in dcoef for secular variation terms.
        for n, m, gnm, hnm, dgnm, dhnm in rows:
            if m <= n:
                coef[m][n] = gnm
                dcoef[m][n] = dgnm
                if m != 0:
                    coef[n][m - 1] = hnm
                    dcoef[n][m - 1] = dhnm

        snorm = _z(sz)
        k = _z(sz)
        snorm[0][0] = 1.0

        fn = [0.0] + [float(n + 1) for n in range(1, maxord + 1)]
        fm = [float(m) for m in range(maxord + 1)]

        for n in range(1, maxord + 1):
            snorm[0][n] = snorm[0][n - 1] * (2.0 * n - 1) / n
            j = 2.0
            for m in range(n + 1):
                k[m][n] = ((n - 1)**2 - m**2) / ((2.0 * n - 1) * (2.0 * n - 3.0))
                if m > 0:
                    flnmj = ((n - m + 1.0) * j) / (n + m)
                    snorm[m][n] = snorm[m - 1][n] * math.sqrt(flnmj)
                    j = 1.0
                    coef[n][m - 1] *= snorm[m][n]
                    dcoef[n][m - 1] *= snorm[m][n]
                coef[m][n] *= snorm[m][n]
                dcoef[m][n] *= snorm[m][n]

        self._maxord = maxord
        self._sz = sz
        self._c = coef
        self._cd = dcoef
        self._k = k
        self._fn = fn
        self._fm = fm

    # ------------------------------------------------------------------
    # public compute interface
    # ------------------------------------------------------------------

    def compute(self, lat: float, lon: float, alt_km: float,
                date_str: str) -> MagResult:
        """
        Compute all magnetic field components.

        Parameters
        ----------
        lat : float     Geodetic latitude, degrees  (−90 … +90)
        lon : float     Longitude, degrees           (−180 … +180)
        alt_km : float  Altitude above WGS-84 ellipsoid, km
        date_str : str  ISO date string, e.g. '2024-06-17'

        Returns
        -------
        MagResult
        """
        maxord = self._maxord
        dt = _decimal_year(date_str) - self.epoch

        rlat = math.radians(lat)
        rlon = math.radians(lon)
        srlat = math.sin(rlat)
        crlat = math.cos(rlat)
        srlat2 = srlat * srlat
        crlat2 = crlat * crlat

        # ----- geodetic → geocentric -----
        q = math.sqrt(_A2 - _C2 * srlat2)
        q1 = alt_km * q
        q2 = ((q1 + _A2) / (q1 + _B2)) ** 2
        ct = srlat / math.sqrt(q2 * crlat2 + srlat2)
        st = math.sqrt(max(0.0, 1.0 - ct * ct))
        r2 = alt_km**2 + 2.0 * q1 + (_A4 - _C4 * srlat2) / (q * q)
        r = math.sqrt(r2)
        d = math.sqrt(_A2 * crlat2 + _B2 * srlat2)
        ca = (alt_km + d) / r
        sa = _C2 * crlat * srlat / (r * d)

        # ----- longitude trig -----
        # Use pre-allocated buffers (WMM instances are LRU-cached singletons)
        sp = self._buf_sp; cp = self._buf_cp
        p = self._buf_p; dp = self._buf_dp
        pp = self._buf_pp; tc = self._buf_tc

        sp[0] = 0.0; cp[0] = 1.0
        sp[1] = math.sin(rlon)
        cp[1] = math.cos(rlon)
        for m in range(2, maxord + 1):
            sp[m] = sp[1] * cp[m - 1] + cp[1] * sp[m - 1]
            cp[m] = cp[1] * cp[m - 1] - sp[1] * sp[m - 1]

        # ----- Legendre functions and time-adjusted coefficients -----
        p[0][0] = 1.0
        pp[0] = 1.0

        # ----- main SH loop -----
        aor = _RE / r
        ar = aor * aor
        br = bt = bp = bpp = 0.0

        for n in range(1, maxord + 1):
            ar *= aor
            for m in range(n + 1):
                # Legendre recursion
                if n == m:
                    p[m][n] = st * p[m - 1][n - 1]
                    dp[m][n] = st * dp[m - 1][n - 1] + ct * p[m - 1][n - 1]
                elif n == 1 and m == 0:
                    p[m][n] = ct * p[m][n - 1]
                    dp[m][n] = ct * dp[m][n - 1] - st * p[m][n - 1]
                else:
                    if m > n - 2: p[m][n - 2] = 0.0
                    if m > n - 2: dp[m][n - 2] = 0.0
                    p[m][n] = ct * p[m][n - 1] - self._k[m][n] * p[m][n - 2]
                    dp[m][n] = ct * dp[m][n - 1] - st * p[m][n - 1] - self._k[m][n] * dp[m][n - 2]

                # Time-adjust coefficients
                tc[m][n] = self._c[m][n] + dt * self._cd[m][n]
                if m != 0:
                    tc[n][m - 1] = self._c[n][m - 1] + dt * self._cd[n][m - 1]

                # Accumulate field
                par = ar * p[m][n]
                if m == 0:
                    temp1 = tc[m][n] * cp[m]
                    temp2 = tc[m][n] * sp[m]
                else:
                    temp1 = tc[m][n] * cp[m] + tc[n][m - 1] * sp[m]
                    temp2 = tc[m][n] * sp[m] - tc[n][m - 1] * cp[m]

                bt -= ar * temp1 * dp[m][n]
                bp += self._fm[m] * temp2 * par
                br += self._fn[n] * temp1 * par

                # Pole special case
                if st == 0.0 and m == 1:
                    if n == 1:
                        pp[n] = pp[n - 1]
                    else:
                        pp[n] = ct * pp[n - 1] - self._k[m][n] * pp[n - 2]
                    bpp += self._fm[m] * temp2 * ar * pp[n]

        if st == 0.0:
            bp = bpp
        else:
            bp /= st

        # ----- rotate to geodetic frame -----
        X = -bt * ca - br * sa   # north component
        Y = bp                # east component
        Z = bt * sa - br * ca   # down component

        H = math.sqrt(X * X + Y * Y)
        F = math.sqrt(H * H + Z * Z)
        D = math.degrees(math.atan2(Y, X))
        I = math.degrees(math.atan2(Z, H))

        return MagResult(D=D, I=I, H=H, X=X, Y=Y, Z=Z, F=F,
                         model=self.name, date=date_str)


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------

def _decimal_year(date_str: str) -> float:
    """Convert 'YYYY-MM-DD' to decimal year."""
    y, m, d = (int(x) for x in date_str.split("-"))
    dt = _date(y, m, d)
    doy = dt.timetuple().tm_yday
    days = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
    return y + (doy - 1) / days


def load_model(name: str) -> WMM:
    """Load a bundled WMM model by name, e.g. 'WMM2020'."""
    candidates = [
        f"{name}.COF",
        f"{name}v2.COF",
    ]
    for fname in candidates:
        p = os.path.join(_DATA_DIR, fname)
        if os.path.exists(p):
            return WMM(p)
    raise FileNotFoundError(
        f"No bundled COF file found for '{name}'. "
        f"Available files: {os.listdir(_DATA_DIR)}"
    )
