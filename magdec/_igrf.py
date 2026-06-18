"""
IGRF-14 spherical harmonic evaluator.

Covers 1900.0–2030.0 using linear interpolation between the 5-year IGRF
definitive epochs (1900–2020) and the predictive 2025 epoch.  Beyond 2025,
secular variation (SV) coefficients are used to extrapolate to 2030.

Algorithm: same SH expansion as _wmm.py (Weiss/geomag.py port), adapted for
IGRF's multi-epoch file format.  The only difference is how coefficients are
time-adjusted: linear interpolation here vs. explicit secular-variation terms
in WMM.

Reference file: igrf14coeffs.txt from BGS / NOAA NCEI, placed in magdec/data/.
"""

import math
import os
from ._wmm import MagResult, _decimal_year, _A2, _B2, _C2, _A4, _B4, _C4, _RE

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


class IGRF:
    """
    IGRF-14 evaluator.  Same interface as :class:`WMM`.

    Parameters
    ----------
    shc_path : str
        Path to igrf14coeffs.txt (BGS/NOAA SHC format).
    """

    def __init__(self, shc_path: str):
        self._load(shc_path)

    # ------------------------------------------------------------------
    # coefficient loading
    # ------------------------------------------------------------------

    def _load(self, path: str):
        raw_g: dict[tuple[int, int], list[float]] = {}
        raw_h: dict[tuple[int, int], list[float]] = {}
        self.epochs: list[float] = []

        with open(path) as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith('#') or stripped.startswith('%'):
                    continue
                parts = stripped.split()
                if parts[0] == 'g/h':
                    # Header: "g/h n m 1900.0 1905.0 ... 2025.0 2025-30"
                    for tok in parts[3:]:
                        try:
                            self.epochs.append(float(tok))
                        except ValueError:
                            pass   # skip '2025-30', 'SV', etc.
                    continue
                if parts[0] not in ('g', 'h'):
                    continue
                try:
                    n, m = int(parts[1]), int(parts[2])
                    vals = [float(v) for v in parts[3:]]
                except (ValueError, IndexError):
                    continue
                if parts[0] == 'g':
                    raw_g[(n, m)] = vals
                else:
                    raw_h[(n, m)] = vals

        n_epochs = len(self.epochs)   # 26 for IGRF-14 (1900..2025)
        maxord = max(n for n, m in raw_g)
        sz = maxord + 2

        # ----- Schmidt semi-normalisation factors (same as WMM) -----
        snorm = [[0.0] * sz for _ in range(sz)]
        k = [[0.0] * sz for _ in range(sz)]
        snorm[0][0] = 1.0
        for n in range(1, maxord + 1):
            snorm[0][n] = snorm[0][n - 1] * (2.0 * n - 1) / n
            j = 2.0
            for m in range(n + 1):
                k[m][n] = ((n - 1) ** 2 - m ** 2) / ((2.0 * n - 1) * (2.0 * n - 3.0))
                if m > 0:
                    flnmj = ((n - m + 1.0) * j) / (n + m)
                    snorm[m][n] = snorm[m - 1][n] * math.sqrt(flnmj)
                    j = 1.0

        fn = [0.0] + [float(n + 1) for n in range(1, maxord + 1)]
        fm = [float(m) for m in range(maxord + 1)]

        # ----- build normalised coefficient arrays for each epoch -----
        def _make_coef(epoch_idx: int) -> list[list[float]]:
            c = [[0.0] * sz for _ in range(sz)]
            for (n, m), vals in raw_g.items():
                if epoch_idx < len(vals):
                    c[m][n] = vals[epoch_idx] * snorm[m][n]
            for (n, m), vals in raw_h.items():
                if m > 0 and epoch_idx < len(vals):
                    c[n][m - 1] = vals[epoch_idx] * snorm[m][n]
            return c

        # Epoch coefficients: indices 0..n_epochs-1  →  1900..2025
        # SV coefficients:    index n_epochs          →  2025-30 column
        self._coefs = [_make_coef(i) for i in range(n_epochs)]
        self._coef_sv = _make_coef(n_epochs)   # last column = secular variation

        # ----- pre-compute inter-epoch rates (nT / year) -----
        # _rates[i]: rate from epochs[i] to epochs[i+1]  (i = 0..n_epochs-2)
        # _rates[n_epochs-1]: SV rate for extrapolation beyond epochs[-1]
        rates = []
        for i in range(n_epochs - 1):
            interval = self.epochs[i + 1] - self.epochs[i]
            c0 = self._coefs[i]
            c1 = self._coefs[i + 1]
            rate = [[(c1[r][cc] - c0[r][cc]) / interval for cc in range(sz)]
                    for r in range(sz)]
            rates.append(rate)
        rates.append(self._coef_sv)   # SV is already in nT/year
        self._rates = rates

        self._k = k
        self._fn = fn
        self._fm = fm
        self._maxord = maxord
        self._sz = sz
        self.name = "IGRF14"
        self.epoch = self.epochs[0] if self.epochs else 1900.0

        # Pre-allocate per-instance compute buffers (not thread-safe, but
        # instances are LRU-cached singletons so only one thread uses each)
        self._buf_sp = [0.0] * sz
        self._buf_cp = [0.0] * sz
        self._buf_pp = [0.0] * sz
        self._buf_p = [[0.0] * sz for _ in range(sz)]
        self._buf_dp = [[0.0] * sz for _ in range(sz)]

    # ------------------------------------------------------------------
    # public compute interface
    # ------------------------------------------------------------------

    def compute(self, lat: float, lon: float, alt_km: float,
                date_str: str) -> MagResult:
        """
        Compute all magnetic field components.

        Parameters match :meth:`WMM.compute` exactly.
        """
        maxord = self._maxord
        dy = _decimal_year(date_str)

        # ----- find epoch interval and time offset -----
        epochs = self.epochs
        last_epoch = epochs[-1]

        if dy >= last_epoch:
            # Extrapolate beyond 2025 using SV
            c0 = self._coefs[-1]
            rate = self._rates[-1]
            dt_local = dy - last_epoch
        else:
            # Linear search for bracketing epochs (26 entries — not worth bisect)
            idx = 0
            for i in range(len(epochs) - 1):
                if epochs[i] <= dy:
                    idx = i
            c0 = self._coefs[idx]
            rate = self._rates[idx]
            dt_local = dy - epochs[idx]

        # ----- geodetic → geocentric (same as WMM) -----
        rlat = math.radians(lat)
        rlon = math.radians(lon)
        srlat = math.sin(rlat)
        crlat = math.cos(rlat)
        srlat2 = srlat * srlat
        crlat2 = crlat * crlat

        q = math.sqrt(_A2 - _C2 * srlat2)
        q1 = alt_km * q
        q2 = ((q1 + _A2) / (q1 + _B2)) ** 2
        ct = srlat / math.sqrt(q2 * crlat2 + srlat2)
        st = math.sqrt(max(0.0, 1.0 - ct * ct))
        r2 = alt_km ** 2 + 2.0 * q1 + (_A4 - _C4 * srlat2) / (q * q)
        r = math.sqrt(r2)
        d = math.sqrt(_A2 * crlat2 + _B2 * srlat2)
        ca = (alt_km + d) / r
        sa = _C2 * crlat * srlat / (r * d)

        # ----- longitude trig -----
        sp = self._buf_sp; cp = self._buf_cp
        p = self._buf_p; dp = self._buf_dp
        pp = self._buf_pp

        sp[0] = 0.0; cp[0] = 1.0
        sp[1] = math.sin(rlon)
        cp[1] = math.cos(rlon)
        for m in range(2, maxord + 1):
            sp[m] = sp[1] * cp[m - 1] + cp[1] * sp[m - 1]
            cp[m] = cp[1] * cp[m - 1] - sp[1] * sp[m - 1]

        p[0][0] = 1.0
        pp[0] = 1.0

        # ----- main SH loop (identical structure to WMM) -----
        aor = _RE / r
        ar = aor * aor
        br = bt = bp = bpp = 0.0
        k = self._k; fn = self._fn; fm = self._fm

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
                    if m > n - 2:
                        p[m][n - 2] = 0.0
                        dp[m][n - 2] = 0.0
                    p[m][n] = ct * p[m][n - 1] - k[m][n] * p[m][n - 2]
                    dp[m][n] = ct * dp[m][n - 1] - st * p[m][n - 1] - k[m][n] * dp[m][n - 2]

                # Time-interpolated coefficients (inline, avoids tc buffer allocation)
                tc_mn = c0[m][n] + dt_local * rate[m][n]
                if m != 0:
                    tc_nm1 = c0[n][m - 1] + dt_local * rate[n][m - 1]

                par = ar * p[m][n]
                if m == 0:
                    temp1 = tc_mn * cp[m]
                    temp2 = tc_mn * sp[m]
                else:
                    temp1 = tc_mn * cp[m] + tc_nm1 * sp[m]
                    temp2 = tc_mn * sp[m] - tc_nm1 * cp[m]

                bt -= ar * temp1 * dp[m][n]
                bp += fm[m] * temp2 * par
                br += fn[n] * temp1 * par

                # Pole special case
                if st == 0.0 and m == 1:
                    if n == 1:
                        pp[n] = pp[n - 1]
                    else:
                        pp[n] = ct * pp[n - 1] - k[m][n] * pp[n - 2]
                    bpp += fm[m] * temp2 * ar * pp[n]

        if st == 0.0:
            bp = bpp
        else:
            bp /= st

        # ----- rotate to geodetic frame -----
        X = -bt * ca - br * sa
        Y = bp
        Z = bt * sa - br * ca

        H = math.sqrt(X * X + Y * Y)
        F = math.sqrt(H * H + Z * Z)
        D = math.degrees(math.atan2(Y, X))
        I = math.degrees(math.atan2(Z, H))

        return MagResult(D=D, I=I, H=H, X=X, Y=Y, Z=Z, F=F,
                         model=self.name, date=date_str)
