# Purpose: Several functions for analysis data quality and geometry of channels
# Author: Minzhe Hu, Zefeng Li
# Date: 2024.3.26
# Email: hmz2018@mail.ustc.edu.cn
import numpy as np
from copy import deepcopy
from geographiclib.geodesic import Geodesic
from pyproj import Proj


def robust_polyfit(data, deg, thresh):
    """
    Fit a curve with a robust weighted polynomial.

    :param data: 1-dimensional array.
    :param deg: int. Degree of the fitting polynomial
    :param thresh: int or float. Defined MAD multiple of outliers.
    :return: Fitting data
    """
    nch = len(data)
    channels = np.arange(nch)
    p_coef = np.polyfit(channels, data, deg)
    p_fit = np.poly1d(p_coef)
    old_data = p_fit(channels)
    mse = 1

    # robust fitting until the fitting curve changes < 0.1% at every point.
    while mse > 0.001:
        rsl = abs(data - old_data)
        mad = np.median(rsl)
        weights = np.zeros(nch)
        weights[rsl < thresh * mad] = 1
        p_coef = np.polyfit(channels, data, deg, w=weights)
        p_fit = np.poly1d(p_coef)
        new_data = p_fit(channels)
        mse = np.nanmax(np.abs((new_data - old_data) / old_data))
        old_data = new_data

    return new_data, weights


def _continuity_checking(lst1, lst2, adjacent=2, toleration=2):
    lst1_raw = deepcopy(lst1)
    for chn in lst1_raw:
        discont = [a for a in lst2 if abs(a - chn) <= adjacent]
        if len(discont) >= adjacent * 2 + 1 - toleration:
            lst1.remove(chn)
            lst2.append(chn)

    return lst1, lst2


def channel_checking(data, deg=10, thresh=5, continuity=True, adjacent=2,
                     toleration=2, verbose=False):
    """
    Use the energy of each channel to determine which channels are bad.

    :param data: 2-dimensional np.ndarray. Axis 0 is channel number and axis 1 is
        time series
    :param deg: int. Degree of the fitting polynomial
    :param thresh: int or float. The MAD multiple of bad channel energy lower
        than good channels.
    :param continuity: bool. Perform continuity checks on bad channels and good
        channels.
    :param adjacent: int. The number of nearby channels for continuity checks.
    :param toleration: int. The number of discontinuous channel allowed in each
        channel (including itself) in the continuity check.
    :param plot: bool or str. False means no plotting. Str or True means
        plotting while str gives a non-default filename.
    :return: Good channels and bad channels.
    """
    nch = len(data)
    energy = np.log10(np.sum(data**2, axis=1))

    # Remove abnormal value by robust polynomial fitting.
    fitted_energy, weights = robust_polyfit(energy, deg, thresh)
    deviation = energy - fitted_energy

    # Iterate eliminates outliers.
    mad = np.median(abs(deviation[weights > 0]))
    bad_chn = np.argwhere(deviation < -thresh * mad).ravel().tolist()
    good_chn = list(set(range(nch)) - set(bad_chn))

    if continuity:
        # Discontinuous normal value are part of bad channels.
        good_chn, bad_chn = _continuity_checking(good_chn, bad_chn,
                                                 adjacent=adjacent,
                                                 toleration=toleration)

        # Discontinuous outliers are usually not bad channels.
        bad_chn, good_chn = _continuity_checking(bad_chn, good_chn,
                                                 adjacent=adjacent,
                                                 toleration=toleration)

    bad_chn = np.sort(np.array(bad_chn))
    good_chn = np.sort(np.array(good_chn))
    if verbose:
        return good_chn, bad_chn, energy, fitted_energy - thresh * mad

    return good_chn, bad_chn


def channel_location(tx, ty, tn):
    l_track = np.sqrt(np.diff(tx) ** 2 + np.diff(ty) ** 2)
    l_track_cum = np.hstack(([0], np.cumsum(l_track)))
    idx_kp = np.where(tn >= 0)[0]

    interp_ch = []
    chn = np.floor(tn[idx_kp[0]])
    if abs(chn - tn[idx_kp[0]]) < 1e-6:
        interp_ch.append([[tx[idx_kp[0]], ty[idx_kp[0]], chn]])

    seg_interval = []
    for i in range(1, len(idx_kp)):
        # calculate actual interval between known-channel points
        istart, iend = idx_kp[i - 1], idx_kp[i]
        n_chn_kp = tn[iend] - tn[istart]
        d_interp = (l_track_cum[iend] - l_track_cum[istart]) / n_chn_kp
        seg_interval.append([tn[istart], tn[iend], d_interp])

        l_res = 0  # remaining fiber length before counting the next segment
        # consider if the given channelnumber is not an integer
        chn_res = tn[istart] - int(tn[istart])
        for j in range(istart, iend):
            l_start = l_track[j] + l_res

            # if tp segment length is large for more than one interval, get the
            # channel loc
            if l_start >= d_interp * (1 - chn_res):
                # floor int, num of channel available
                n_chn_tp = int(l_start / d_interp + chn_res)
                l_new = (np.arange(n_chn_tp) + 1 - chn_res) * d_interp - \
                    l_res  # channel distance from segment start

                # interpolate the channel loc
                tx_new = np.interp(l_new, [0, l_track[j]], [tx[j], tx[j + 1]])
                ty_new = np.interp(l_new, [0, l_track[j]], [ty[j], ty[j + 1]])
                # fx = interp1d([0, l_track[j + 1]], [tx[j], tx[j + 1]])
                # fy = interp1d([0, l_track[j + 1]], [ty[j], ty[j + 1]])
                # tx_new, ty_new = fx(l_new), fy(x_new)

                # remaining length to add to next segment
                l_res = l_start - n_chn_tp * d_interp

                # write interpolated channel loc
                for (xi, yi) in zip(tx_new, ty_new):
                    chn += 1
                    interp_ch.append([xi, yi, chn])

                # handle floor int problem when l_start/d_interp is near an
                # interger
                if (d_interp - l_res) / d_interp < 1e-6:
                    chn += 1
                    interp_ch.append([tx[j + 1], ty[j + 1], int(tn[j + 1])])
                    l_res = 0
                chn_res = 0
            # if tp segment length is not enough for one interval, simply add
            # the length to next segment
            elif l_start < d_interp:
                l_res = l_start

    return np.array(seg_interval), np.array(interp_ch)


def location_interpolation(known_pt, track_pt=None, dx=None, data_type='lonlat',
                           verbose=False):
    """
    Interpolate to obtain the positions of all channels.

    :param known_pt: N*3 np.ndarray. Points with known channel numbers. Each row
        includes two coordinates and a channel number.
    :param track_pt: M*2 np.ndarray. Optional fiber spatial track points without
        channel numbers. Each row includes two coordinates.
    :param dx: Known points far from the track (> dx) will be excluded.
        Recommended setting is channel interval. The unit is m.
    :param data_type: str. Coordinate type. 'latlon' for latitude and longitude,
        'xy' for x and y.
    :param verbose: bool. If True, return interpoleted channel location and
        segment interval.
    :return: Interpoleted channel location if verbose is False.
    """
    if data_type == 'lonlat':
        klo, kla, kn = known_pt.T
        zone = np.floor((max(klo) + min(klo)) / 2 / 6).astype(int) + 31
        DASProj = Proj(proj='utm', zone=zone, ellps='WGS84',
                       preserve_units=False)
        kx, ky = DASProj(klo, kla)
    elif data_type == 'xy':
        kx, ky, kn = known_pt.T
    
    if track_pt is None:
        seg_interval, interp_ch = channel_location(kx, ky, kn)
    else:
        if data_type == 'lonlat':
            tlo, tla = track_pt.T
            tx, ty = DASProj(tlo, tla)
        elif data_type == 'xy':
            tx, ty = track_pt.T
        
        tn = np.zeros(len(track_pt)) - 1

        # insert the known points into the fiber track data
        K = len(klo)
        dx_matrix = np.tile(tx, (len(kx), 1)) - np.tile(kx, (len(tx), 1)).T
        dy_matrix = np.tile(ty, (len(ky), 1)) - np.tile(ky, (len(ty), 1)).T
        d = np.sqrt(dx_matrix ** 2 + dy_matrix ** 2)
        idx = np.argmin(d, axis=1)
        for i in range(K):
            if d[i, idx[i]] < dx:
                tn[idx[i]] = kn[i]
                last_pt = idx[i]

        # interpolation with regular spacing along the fiber track
        try:
            tx, ty, tn = tx[:last_pt + 1], ty[:last_pt + 1], tn[:last_pt + 1]
        except NameError:
            print('All known points are too far away from the track points.' +
                  'If they are reliable, they can be merged in sequence as' +
                  'track points to input')
            return None
        seg_interval, interp_ch = channel_location(tx, ty, tn)

    if data_type == 'lonlat':
        interp_ch[:, 1], interp_ch[:, 0] = \
                DASProj(interp_ch[:, 0], interp_ch[:, 1], inverse=True)

    if verbose:
        return interp_ch, seg_interval
    return interp_ch


def _xcorr(x, y):
    N = len(x)
    meanx = np.mean(x)
    meany = np.mean(y)
    stdx = np.std(np.asarray(x))
    stdy = np.std(np.asarray(y))
    c = np.sum((y - meany) * (x - meanx)) / (N * stdx * stdy)
    return c


def _horizontal_angle_change(geo, gap=10):
    nch = len(geo)
    angle = np.zeros(nch)
    for i in range(1, nch - 1):
        lat, lon = geo[i]
        lat_s, lon_s = geo[max(i - gap, 0)]
        lat_e, lon_e = geo[min(i + gap, nch - 1)]
        azi_s = Geodesic.WGS84.Inverse(lat_s, lon_s, lat, lon)['azi1']
        azi_e = Geodesic.WGS84.Inverse(lat, lon, lat_e, lon_e)['azi1']
        dazi = azi_e - azi_s
        if abs(dazi) > 180:
            dazi = -np.sign(dazi) * (360 - abs(dazi))
        angle[i] = dazi

    return angle


def _vertical_angle_change(geo, gap=10):
    nch = len(geo)
    angle = np.zeros(nch)
    for i in range(1, nch - 1):
        lat, lon, dep = geo[i]
        lat_s, lon_s, dep_s = geo[max(i - gap, 0)]
        lat_e, lon_e, dep_e = geo[min(i + gap, nch - 1)]
        s12_s = Geodesic.WGS84.Inverse(lat_s, lon_s, lat, lon)['s12']
        theta_s = np.arctan((dep - dep_s) / s12_s) / np.pi * 180
        s12_e = Geodesic.WGS84.Inverse(lat, lon, lat_e, lon_e)['s12']
        theta_e = np.arctan((dep_e - dep) / s12_e) / np.pi * 180
        angle[i] = theta_e - theta_s

    return angle


def _local_maximum_indexes(data, thresh):
    idx = np.where(data > thresh)[0]
    i = list(np.where(np.diff(idx) > 1)[0] + 1)
    if len(idx) - 1 not in i:
        i.append(len(idx) - 1)
    b = 0
    max_idx = []
    for e in i:
        max_idx.append(idx[b] + np.argmax(data[idx[b]:idx[e]]))
        b = e

    return max_idx


def turning_points(data, data_type='coordinate', thresh=5, depth_info=False,
                   channel_gap=3):
    """
    Seek turning points in the DAS channel.

    :param data: numpy.ndarray. Data used to seek turning points.
    :param data_type: str. If data_type is 'coordinate', data should include
        latitude and longitude (first two columns), and can also include depth
        (last column). If data_type is 'waveform', data should be continuous
        waveform, preferably containing signal with strong coherence
        (earthquake, traffic signal, etc.).
    :param thresh: For coordinate data, when the angle of the optical cables on
        both sides centered on a certain point exceeds thresh, it is considered
        an turning point. For waveform, thresh means the MAD multiple of
        adjacent channel cross-correlation values lower than their median.
    :param depth_info: bool. Optional if data_type is 'coordinate'. Whether
        depth (in meters) is included in the coordinate data and need to be
        used.
    :param channel_gap: int. Optional if data_type is 'coordinate'. The smaller
        the value is, the finer the segmentation will be. It is recommended to
        set it to half the ratio of gauge length and channel interval.
    :return: list. Channel index of turning points.
    """
    if data_type == 'coordinate':
        angle = _horizontal_angle_change(data[:, :2], gap=channel_gap)
        turning_h = _local_maximum_indexes(abs(angle), thresh)

        if depth_info:
            angle = _vertical_angle_change(data, gap=channel_gap)
            turning_v = _local_maximum_indexes(abs(angle), thresh)
            return turning_h, turning_v

        return turning_h

    elif data_type == 'waveform':
        nch = len(data)
        cc = np.zeros(nch - 1)
        for i in range(nch - 1):
            cc[i] = _xcorr(data[i], data[i + 1])
        median = np.median(cc)
        mad = np.median(abs(cc - median))

        return np.argwhere(cc < median - thresh * mad)[0] - 0.5

    else:
        raise ValueError('Data_type should be \'coordinate\' or \'waveform\'.')
