# Purpose: Some preprocess methods
# Author: Minzhe Hu
# Date: 2024.4.11
# Email: hmz2018@mail.ustc.edu.cn
import numpy as np
from scipy.signal import detrend
from scipy.signal.windows import tukey
from daspy.basic_tools.filter import lowpass_cheby_2


def phase2strain(data, lam, e, n, gl):
    """
    Convert the optical phase shift in radians to strain.

    :param data: numpy.ndarray. Data to convert.
    :param lam: float. Operational optical wavelength in vacuum.
    :param e: float. photo-slastic scaling factor for logitudinal strain in
        isotropic material.
    :param n: float. Refractive index of the sensing fiber.
    :paran gl: float. Gauge length.
    :return: Strain data.
    """
    return data * (lam * 1e-9) / (e * 4 * np.pi * n * gl)


def normalization(data, method='z-score'):
    """
    Normalize for each individual channel using Z-score method.

    :param data: numpy.ndarray. Data to normalize.
    :param method: str. Method for normalization, should be one of 'max' or
        'z-score'.
    :return: Normalized data.
    """
    if len(data.shape) == 1:
        data = data.reshape(1, len(data))
    elif len(data.shape) != 2:
        raise ValueError("Data should be 1-D or 2-D array")
    nt = len(data[0])
    if method == 'max':
        amp = np.tile(np.max(abs(data), 1), (nt, 1)).T
        amp[amp == 0] = amp[amp > 0].min()
        return data / amp

    if method == 'z-score':
        mean = np.tile(np.mean(data, axis=1), (nt, 1)).T
        std = np.tile(np.std(data, axis=1), (nt, 1)).T
        std[std == 0] = std[std > 0].min()
        return (data - mean) / std


def demeaning(data):
    """
    Demean signal by subtracted mean of each channel.

    :param data: numpy.ndarray. Data to demean.
    :return: Detrended data.
    """
    return detrend(data, type='constant')


def detrending(data):
    """
    Detrend signal by subtracted a linear least-squares fit to data.

    :param data: numpy.ndarray. Data to detrend.
    :return: Detrended data.
    """
    return detrend(data, type='linear')


def stacking(data, N, step=None):
    """
    Stack several channels to increase the signal-noise ratio(SNR).

    :param data: numpy.ndarray. Data to stack.
    :param N: int. N adjacent channels stacked into 1.
    :param step: int. Interval of data stacking.
    :return: Stacked data.
    """
    if step is None:
        step = N
    nch, nt = data.shape
    begin = np.arange(0, nch - N + 1, step)
    end = begin + N
    nx1 = len(begin)
    data_stacked = np.zeros((nx1, nt))
    for i in range(nx1):
        data_stacked[i, :] = np.mean(data[begin[i]:end[i], :], axis=0)
    return data_stacked


def cosine_taper(data, p=0.1):
    """
    Taper using Tukey window.

    :param data: numpy.ndarray. Data to taper.
    :param p: float or sequence of floats. Each float means decimal percentage
        of Tukey taper for corresponding dimension (ranging from 0 to 1).
        Default is 0.1 which tapers 5% from the beginning and 5% from the end.
        If only one float is given, it only do for time dimension.
    :return: Tapered data.
    """
    if len(data.shape) == 1:
        return data * tukey(len(data), p)
    nch, nt = data.shape
    win = np.ones_like(data)
    if not isinstance(p, (tuple, list, np.ndarray)):
        p = (0, p)

    win *= np.tile(tukey(nch, p[0]), (nt, 1)).T
    win *= np.tile(tukey(nt, p[1]), (nch, 1))
    return data * win


def downsampling(data, xint=None, tint=None, stack=True, filter=True):
    """
    Downsample DAS data.

    :param data: numpy.ndarray. Data to downsample can be 1-D or 2-D.
    :param xint: int. Spatial downsampling factor.
    :param tint: int. Time downsampling factor.
    :param stack: bool. If True, stacking will replace decimation.
    :param filter: bool. Filter before time downsampling or not.
    :return: Downsampled data.
    """
    data_ds = data.copy()
    if xint:
        if stack:
            data_ds = stacking(data, xint)
        else:
            data_ds = data_ds[::xint]
    if tint:
        if filter:
            data_ds = lowpass_cheby_2(detrending(data_ds), 1, 1 / 2 / tint)
        if len(data_ds.shape) == 1:
            data_ds = data_ds[::tint]
        else:
            data_ds = data_ds[:, ::tint]
    return data_ds


def trimming(data, dx=None, fs=None, xmin=0, xmax=None, tmin=0, tmax=None,
             mode=0):
    """
    Cut data to given start and end distance/channel or time/sampling points.

    :param data: numpy.ndarray. Data to trim can be 1-D or 2-D.
    :param dx: Channel interval in m.
    :param fs: Sampling rate in Hz.
    :param xmin, xmax, tmin, tmax: Boundary for trimming.
    :param mode: 0 means the unit of boundary is channel number and sampling
        points; 1 means the unit of boundary is meters and seconds.
    :return: Trimmed data.
    """
    nch, nt = data.shape
    if mode == 0:
        if xmax is None:
            xmax = nch
        if tmax is None:
            tmax = nt
    elif mode == 1:
        xmin = round(xmin / dx)
        xmax = (round(xmax / dx), nch)[xmax is None]
        tmin = round(tmin * fs)
        tmax = (round(tmax * fs), nt)[tmax is None]

    return data[xmin:xmax, tmin:tmax]


def padding(data, dn, reverse=False):
    """
    Pad DAS data with 0.

    :param data: numpy.ndarray. 2D DAS data to pad.
    :param dn: int or sequence of ints. Number of points to pad for both
        dimensions.
    :param reverse: bool. Set True to reverse the operation.
    :return: Padded data.
    """
    nch, nt = data.shape
    if isinstance(dn, int):
        dn = (dn, dn)

    pad = (dn[0] // 2, dn[0] - dn[0] // 2, dn[1] // 2, dn[1] - dn[1] // 2)
    if reverse:
        return data[pad[0]:nch - pad[1], pad[2]:nt - pad[3]]
    else:
        data_pd = np.zeros((nch + dn[0], nt + dn[1]))
        data_pd[pad[0]:nch + pad[0], pad[2]:nt + pad[2]] = data
        return data_pd


def time_integration(data, fs):
    """
    Integrate DAS data in time.

    :param data: numpy.ndarray. 2D DAS data to pad.
    :param fs: Sampling rate in Hz.
    :return: Integrated data.
    """
    return np.cumsum(data, axis=1) / fs


def time_differential(data, fs):
    """
    Differentiate DAS data in time.

    :param data: numpy.ndarray. 2D DAS data to pad.
    :param fs: Sampling rate in Hz.
    :return: Differentiated data.
    """
    return np.diff(data, axis=1) / fs
