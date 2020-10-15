# -*- coding: utf-8 -*-
"""

Generate stretched vertical grid for WRF using a smooth variation in the
stretching in eta. Two different types of grids can be constructed, a three-
layer and a two-layer grid. See the code for more.

Authors
-------
Stefano Serafin and Matthias Göbel
    - stretching functions
Lukas Strauss and Matthias Göbel
    - plotting, testing

"""

#-------------------------------------------------------------------------------
# MODULES
#-------------------------------------------------------------------------------
# Import modules.
import numpy as np


from metpy import calc as metcalc
from metpy.units import units as metunits
from metpy import constants as metconst
import scipy as sp
import os
import matplotlib
import matplotlib.pyplot as plt
from matplotlib import rc
import xarray as xr
import scipy as sp
import math
# rc('text',usetex=True)
# rc('text.latex', preamble=r'\usepackage{color}')
# from matplotlib.backends.backend_pgf import FigureCanvasPgf
# matplotlib.backend_bases.register_backend('pdf', FigureCanvasPgf)

# pgf_with_latex = {
#     "pgf.texsystem": "pdflatex",     # Use xetex for processing
#     "text.usetex": True,            # use LaTeX to write all text
#     "pgf.rcfonts": False,           # Ignore Matplotlibrc
#     "pgf.preamble": [
#         r'\usepackage{xcolor}'     # xcolor for colours
#     ]
# }
# matplotlib.rcParams.update(pgf_with_latex)

figloc = "~/"
figloc = os.path.expanduser(figloc)
#-------------------------------------------------------------------------------
# FUNCTIONS
#-------------------------------------------------------------------------------
def calc_B_hybrid(eta, eta_c=0.2):
    b = eta_c
    b2 = b**2
    c1 = 2*b2
    c2 = -b*(4+b+b2)
    c3 = 2*(1+b+b2)
    c4 = -1 - b
    B = (c1 + c2*eta + c3*eta**2 + c4*eta**3)/(1-b)**3
    B = np.where(eta < eta_c, 0, B)

    return B

def pd_from_eta_hybrid(eta, eta_c=0.2, pt=100, ps=1013.25, p0=1013.25):
    """
    Calculate dry pressure corresponding to WRF hybrid eta coordinate
    value using the US standard atmosphere

    Parameters
    ----------
    eta : float
        eta value (0 to 1).
    eta_c : float, optional
        eta value where coordinate becomes isobaric. The default is 0.2.
    pt : float, optional
        pressure at model top (hPa). The default is 100.
    ps : float, optional
        pressure at surface (hPa). The default is 1000.
    p0 : float, optional
        reference sea-level pressure (hPa). The default is 1000.

    Returns
    -------
    pd : float
        dry pressure (hPa).

    """


    B = calc_B_hybrid(eta, eta_c)
    pd = B*(ps-pt) + (eta-B)*(p0-pt) + pt

    return pd

def height_from_eta(eta, eta_c=0.2, pt=100, ps=1013.25, p0=1013.25, **kwargs):
    """
    Calculate height corresponding to WRF hybrid eta coordinate
    value using the US standard atmosphere

    Parameters
    ----------
    eta : float
        eta value (0 to 1).
    eta_c : float, optional
        eta value where coordinate becomes isobaric. The default is 0.2.
    pt : float, optional
        pressure at model top (hPa). The default is 100.
    ps : float, optional
        pressure at surface (hPa). The default is 1000.
    p0 : float, optional
        reference sea-level pressure (hPa). The default is 1000.

    Returns
    -------
    z : float
        height (m).

    """
    pd = pd_from_eta_hybrid(eta, eta_c, pt, ps, p0)*metunits.hPa
    z = pressure_to_height_std(pd, p0=p0, **kwargs)

    return z
#%%

def pressure_from_theta(theta, p0=1e5):
    """Calculate pressure from potential temperature and surface pressure"""
    cp = metconst.Cp_d
    g = metconst.g
    c = (metconst.Cp_d/metconst.Rd).m/1000
    integral = -sp.integrate.cumtrapz(1/theta.values, theta.level.values)*metunits.meter/metunits.K
    p = theta.copy()
    if "unit" in dir(p0):
        units = p0.units
    else:
        units = ""
    p = p.assign_attrs(units=units)
    pt = p0*(g/cp*integral + 1)**c
    p[:] =  np.concatenate(([p0],pt))

    return p

def strheta_1(nlev, etaz1, etaz2, deta0, detamax=None, n2=None):
    """Generate a three-layer grid.

    The grid spacing is constant in the first and third layer.

    Parameters
    ----------
    nlev : int
        Number of vertical levels.
    etaz1 : float
        Bottom of the second layer.
    etaz2 : float
        Bottom of the third layer.
    deta0 : float
        Grid spacing in eta in the first layer.
    n2 : int
        Number of levels in the third layer.

    Returns
    -------
    eta : np.ndarray
        Eta levels.
    deta : np.ndarray
        Eta level spacings.

    """

    # Determine the number of grid points in the two lowest layers,
    # numbered 0-1-2 bottom to top

    n0 = int((1.-etaz1)/deta0)

    # The delta eta in the upper layer is necessarily determined by the
    # stretching function in the intermediate layer (see below)
    if detamax is None:
        n1 = int(nlev - n0 - n2 - 1)
        detamax = 2.*(etaz1-etaz2)/n1-deta0
    else:
        n2 = int(2.*(etaz1-etaz2)/(detamax+deta0))
        n1 = int(nlev - n0 - n2 - 1)
    if n1 <= 0:
        raise ValueError("Too few vertical levels! Need at least {}!".format(n0+n2+2))

    # Pre-allocate arrays for eta and delta eta

    eta  = np.ones([nlev])
    deta = np.ones([nlev-1])*deta0

    # Layer 0 (bottom): constant deta = deta0

    for i in range(n0):
      deta[i] = deta0
      eta[i+1] = eta[i]-deta[i]

    # Layer 1 (intermediate): deta stretches with a sinusoidal function.
    # Consequently, the stretching factor d(deta)/dj (j=grid point index)
    # is a cosine square function, which varies smoothly and has a maximum in
    # the middle of the stretching layer.
    # The amplitude of the cosine^2 function that describes the stretching
    # is dictated by etaz1, etaz2, deta0 and the number of levels in the
    # stretching layer.
    # It can be demonstrated that deta stretches from deta0 to deta2, with
    # deta2 = 2.*(etaz1-etaz2)/n1-deta0
    # Consequence: there is no guarantee that deta2 = etaz2/n2.

    ampl = 4*(etaz1-etaz2-n1*deta0)/(n1**2)
    for i in range(n0,n0+n1):
      j = i-n0
      deta[i] = deta0 + ampl*(j/2.-n1/(4.*np.pi)*np.sin(2.*np.pi*j/n1))
      eta[i+1] = eta[i]-deta[i]

    # Check that everything is ok, that is, the deta in the uppermost
    # layer (detadum) is exactly as expected (deta2)

    #j = n1
    #detadum = deta0 + ampl*(j/2.-n1/(4.*np.pi)*np.sin(2.*np.pi*j/n1))
    #print deta2, detadum

    # Layer 2 (top): constant deta = deta2

    for i in range(n0+n1,nlev-1):
      deta[i] = detamax
      eta[i+1] = eta[i]-deta[i]

    # Generally, the coordinate of the uppermost level eta.min() will not be
    # exactly zero. Therefore, rescale eta so that its range is exactly 0-1
    # and recompute deta accordingly

    eta = (eta-eta.min())/(eta.max()-eta.min())
    deta = -eta[1:]+eta[:-1]

    return eta, deta

def strheta_2(nlev, etaz1, deta0):
    """Generate a two-layer grid.

    The grid spacing is constant in the first layer and increases in the second.

    Parameters
    ----------
    nlev : int
        Number of vertical levels.
    etaz1 : float
        Bottom of the second layer.
    deta0 : float
        Grid spacing in eta in the first layer.

    Returns
    -------
    eta : np.ndarray
        Eta levels.
    deta : np.ndarray
        Eta level spacings.

    """

    # Determine the number of grid points in the two layers,
    # numbered 0-1 bottom to top

    n0 = int((1.-etaz1)/deta0)
    n1 = int(nlev - n0 - 1)

    # The delta eta at the model top, that is, for the first
    # hypothetical layer above model top, is necessarily determined
    # by the stretching function (see below)

    detamax = deta0+2.*np.pi**2./(np.pi**2.-4.)*(etaz1-deta0*n1)/n1

    # Pre-allocate arrays for eta and delta eta

    eta  = np.ones([nlev])
    deta = np.ones([nlev-1])*deta0

    # Layer 0 (bottom): constant deta = deta0

    for i in range(n0):
      deta[i] = deta0
      eta[i+1] = eta[i]-deta[i]

    # Layer 1: deta stretches with a sinusoidal function.
    # Consequently, the stretching factor d(deta)/dj (j=grid point index)
    # is a cosine square function, which varies smoothly and has a maximum
    # at the domain top.
    # The amplitude of the cosine^2 function that describes the stretching
    # is dictated by etaz1, deta0 and the number of levels in the
    # stretching layer.

    ampl = 4.*np.pi**2./(np.pi**2.-4.)*(etaz1-n1*deta0)/(n1**2.)
    for i in range(n0,nlev-1):
      j = i-n0
      deta[i] = deta0 + ampl*(j/2.-n1/(2.*np.pi)*np.sin(np.pi*j/n1))
      eta[i+1] = eta[i]-deta[i]

    # Check that everything is ok, that is, the deta at the model
    # top (detadum) is exactly as expected (detamax)

    #j=nlev-1-n0
    #detadum = deta0 + ampl*(j/2.-n1/(2.*np.pi)*np.sin(np.pi*j/n1))
    #print detamax, detadum

    # Generally, the coordinate of the uppermost level eta.min() will not be
    # exactly zero. Therefore, rescale eta so that its range is exactly 0-1
    # and recompute deta accordingly

    eta = (eta-eta.min())/(eta.max()-eta.min())
    deta = -eta[1:]+eta[:-1]

    return eta,deta

# def sin_3layer(dz0, dzmax, ztop, z1, z2):

#     n1 = z1/dz0
#     n2 = (ztop-z2)/dzmax

#     if int(n1) != n1:
#         raise ValueError("z1 must be a multiple of dz0!")
#     if int(n2) != n2:
#         raise ValueError("ztop-z2 must be a multiple of dzmax!")
#     if  z1 >= z2:
#         raise ValueError("z1 must be smaller than z2!")

#     dz1 = np.ones(int(n1))*dz0
#     dz3 = np.ones(int(n2))*dzmax
#     dz2 = []
#     a = dzmax - dz0
#     b = (z1 + z2)/2
#     zi = z1
#     while zi <= z2:
#         dzi = (dzmax - dz0)/2*np.sin(np.pi/(z2-z1)*(zi-(z1+z2)/2)) + (dzmax + dz0)/2
#         zi += dzi
#         dz2.append(dzi)
#     dz = [*dz1,*dz2,*dz3]

# dz0 = 50
# nz = 35
# z1 = 200
# z2 = 10000
# ztop = 16000

def tanh_method(ztop, dzmin, dzmax=None, nz=None, D1=0, alpha=1):
    """
    Vertical grid with three layers. Spacing dz=dzmin in the first up to D1, then hyperbolic stretching
    up to D1+D2 and then constant again up to ztop. D2 is calculated automatically. If nz is None, nz is
    calculated from dzmax, while setting D2=ztop.


    Parameters
    ----------
    ztop : float
        domain top (m).
    dzmin : float
        spacing in the first layer (m).
    dzmax : float or None
        spacing in the third layer (m). If None, only two layers are used.
    nz : int
        number of levels or None. If None: 3rd layer is omitted.
    D1 : float
        depth of first layer (m).

    alpha : float, optional
        stretching coefficient. The default is 1.

    Returns
    -------
    z : numpy array of floats
        vertical levels.
    dz : numpy array of floats
        spacing for all levels.

    """

    n1 = D1/dzmin
    if n1 != int(n1):
        raise ValueError("Depth of layer 1 is not a multiple of its grid spacing!")
    n1 = int(n1)
    if nz is None:
        dzm = (dzmin + dzmax)/2
        n2 = math.ceil((ztop-D1)/dzm)
        #recalculate dzm and dzmax
        dzm = (ztop - D1)/n2
        dzmax = 2*dzm - dzmin
        nz = n1 + n2 + 1
        n3 = 0
    elif dzmax is None: #only two layer
           # if nz is None:
        n2 = nz - n1 - 1
        dzm = (ztop - D1)/n2
        n3 = 0
    else:
        #average spacing in intermediate layer
        dzm = (dzmin + dzmax)/2

        #determine n2 from constraints
        n2 = round((ztop - D1 + (n1 - nz + 1)*dzmax)/(dzm-dzmax))
        D2 = dzm*n2
        n3 = nz - 1 - n2 - n1
        D3 = dzmax*n3
        ztop = D1 + D2 + D3
        nz = n1 + n2 + n3 + 1

        for i,n in enumerate((n2,n3)):
            if n != abs(int(n)):
                raise ValueError("Vertical grid creation failed!")# Try more levels, higher grid spacing or lower model top.")

    #get spacing in layer 2 by stretching
    ind = np.arange(1, n2+1)
    a = (1 + n2)/2
    dz2 = dzm + (dzmin - dzm)/np.tanh(2*alpha)*np.tanh(2*alpha*(ind-a)/(1-a))

    #build spacings and levels
    dz = np.concatenate((np.repeat(dzmin, n1), dz2, np.repeat(dzmax, n3)))
    z = np.insert(np.cumsum(dz),0,0).astype(float)
    np.testing.assert_allclose(ztop, z[-1])

    return z, dz


def T_std(ztop, strat=True):
    T0 = 15 + 273.15
    zvals = np.arange(0, ztop + 1, 1)
    T = T0 - 0.0065*zvals
    T = xr.DataArray(T, coords={"z" : zvals}, dims=["z"])
    if (ztop > 11000) and strat:
        T.loc[11000:] = T.loc[11000]
        T.loc[10000:12000] = np.nan
        T = T.interpolate_na("z", method="quadratic")
    return T

def height_to_pressure_std(z, p0=1013.25, return_da=False, **kwargs):
    if np.array(z == 0).all():
        return p0
    ztop = np.array(z).max()
    T = T_std(ztop, **kwargs)
    T_int = sp.integrate.cumtrapz(metconst.g.m/(1000*metconst.Rd.m*T), T.z)
    T_int = np.insert(T_int,0,0)
    p = T.copy()
    p[:] = p0*np.exp(-T_int)
    p = p.interp(z=z)
    if not return_da:
        p = p.values

    return p

def pressure_to_height_std(p, p0=1013.25, **kwargs):
    pstd = height_to_pressure_std(np.linspace(0,20000,20000), p0=p0, return_da=True, **kwargs)
    zstd = xr.DataArray(pstd.z.values, coords={"p":pstd.values}, dims=["p"])
    z = zstd.interp(p=p)
    return z.values
# z, dz = tanh_method(100, 20, 200,12200, 1)
# plt.plot( z[:-1], dz)

# plt.plot(dz)

#%%
def create_levels(ztop, dz0, method=0, nz=None, dzmax=None, theta=None, p0=1000, plot=True, table=True, savefig=False, imgtype="pdf", strat=False, **kwargs):
#for method 0 (linearly increasing dz from dz0 at z=z0 to dzt at z=ztop)
   # dzt = 200
#for method 1 (ARPS method)
#        deta0 = 0.0008
#        etaz1 = 0.999
# for method 2:
        #schmidli:
#        etaz1 = 0.87
#        etaz2 = 0.4
#        detaz0 = 0.0038
#        nz = 143
#        n2 = 37
    z0 = 0
    if (method in [1,2]) and (nz is None):
        raise ValueError("For vertical grid method {}, nz must be defined!".format(nz))
    if method == 0: # linearly increasing dz from dz0 at z=z0 to dzt at z=ztop
        stop = False
        search_nz = False
        if nz is None:
            if dzmax is None:
                raise ValueError("For vertical grid method 0: if nz is not defined, dzmax must be defined!")
            nz = int(ztop/dzmax)
            search_nz = True

        while not stop:
            roots = np.roots((nz - 2)*[dz0]+ [dz0-ztop])
            c = roots[~np.iscomplex(roots)].real
            c = float(c[c > 0])
            #if nz is not given, check if dzmax threshold is reached
            if search_nz:
                dzmax_c = dz0*c**(nz-2)
                if dzmax_c <= dzmax:
                    stop = True
            else:
                stop = True
            if not stop:
                nz += 1

        z = np.zeros(nz)
        for i in range(nz - 1):
            z[i+1] = dz0 + z[i] * c

    elif method == 1: # 2- layer

        detaz0 = dz0/(ztop - dz0)
        etaz, detaz = strheta_2(nz, deta0=detaz0, **kwargs)
        z = ztop + etaz * (z0 - ztop)
    elif method == 2:  # ARPS method 3-layer

        detaz0 = dz0/ztop# - dz0)
        detazmax = None
        if dzmax is not None:
            detazmax = dzmax/ztop
        etaz, detaz = strheta_1(nz, deta0=detaz0, detamax=detazmax, **kwargs)
        z = ztop + etaz * (z0 - ztop)
    elif method == 3:
        z,_ = tanh_method(ztop, dz0, dzmax, nz, **kwargs)

    else:
        raise ValueError("Vertical grid method {} not implemented!".format(method))


    if theta is None:
        # ptop = metcalc.height_to_pressure_std(ztop*metunits.m).m*100
        # p = metcalc.height_to_pressure_std(z*metunits.m).m*100
        ptop = height_to_pressure_std(ztop, p0=p0, strat=strat)*100
        p = height_to_pressure_std(z, p0=p0, strat=strat)*100
    else:
        pth = pressure_from_theta(theta, p0=p0)
        p = pth.interp(level=z, kwargs=dict(fill_value="extrapolate")).values
        ptop = pth.interp(level=ztop, kwargs=dict(fill_value="extrapolate")).values

    if (method != 3) and (np.round(z[-1],3) != ztop):
        raise ValueError("Uppermost level ({}) is not at ztop ({})!".format(z[-1], ztop))

    psfc = p.max()
    # Define stretched grid in pressure-based eta coordinate.
    eta = (p - ptop) / (psfc-ptop)
    eta[0] = 1
    eta[-1] = 0

    # Compute dp, dz and the alphas

    dp = np.diff(p)
    dp = np.append(np.nan, dp)
    dz = z[1:] - z[:-1]
    dz = np.append(dz,np.nan)
    alpha = np.diff(eta)[1:] / np.diff(eta)[:-1]
    alpha = np.append(np.append(np.nan,alpha),np.nan)
    alpha_z = np.diff(z)[1:] / np.diff(z)[:-1]
    alpha_z = np.append(np.append(np.nan,alpha_z),np.nan)
    eps = 1e-6

    #---------------------------------------------------------------------------
    # Make a plot.
    #---------------------------------------------------------------------------

       # Define some reference heights to be drawn in the figure.
    #zPBLref = z0 + 1500
    zPBLref = z0 + 1000
    zTPref = 11000
    if plot:
        fig, ax1a = plt.subplots(figsize=(5, 4))
        ms = 2
        # z
        ax1a.plot(dz, z, 'ko', ms=ms)
        ax1a.set_xlim(0, np.nanmax(dz)+20)
        ax1a.grid(c=(0.8, 0.8, 0.8))
        ax1a.set_ylabel('height (m)')
        ax1a.set_xlabel('$\Delta z$ (m)')

        ax1b = ax1a.twiny()
        ax1b.plot(alpha_z, z, 'o', c="blue", ms=ms)
        xlabel = r"\textcolor{blue}{$\Delta z (i)$/$\Delta z (i-1)$}, \textcolor{red}{$\Delta \eta (i)$/$\Delta \eta (i-1)$}"
        ax1b.set_xlabel(xlabel)
        ax1b.plot(alpha, z, 'o', c="red", ms=ms)

        # alpha_eta

        for ax in [ax1a, ax1b,]:
            ax.set_ylim(0, max(z))
#            ax.axhline(z1, ls='--', c=(0.9, 0.9, 0.9))
            # ax.axhline(zPBLref, ls=':', c='k')
            # ax.axhline(zTPref, ls=':', c='k')
#            ax.axhline(z2, ls='--', c=(0.9, 0.9, 0.9))

        # Save figure.
        if savefig:
            fig.savefig(figloc + '/wrf_stretched_grid_etaz.%s'%imgtype)

    #---------------------------------------------------------------------------
    # Print vertical grid data.
    #---------------------------------------------------------------------------
    printedPBL = False
    printedTP = False
    if table:
        header =  ('|  ml |    eta | p (hPa) | z (m) | -dp (hPa) | dz (m) | '
                   'alpha | alpha_z |')
        print('-'*len(header))
        print('|    With a surface pressure of %7.2f hPa'%(1e-2*psfc))
        print('|   and a model-top pressure of %7.2f hPa'%(1e-2*ptop))
        print('-'*len(header))
        print(header)
        print('-'*len(header))
        for i in range(p.size):
            if z[i] > zPBLref and not printedPBL:
                print('|%s|'%('-'*(len(header)-2)))
                printedPBL = True
            if z[i] > zTPref and not printedTP:
                print('|%s|'%('-'*(len(header)-2)))
                printedTP = True
            print(('| %3i | % 5.3f | %7.0f | %5.0f | %9.1f | %6.0f | %5.3f '
                   '| %7.3f |'%
                   (i, eta[i], 1e-2*p[i], z[i], -1e-2*dp[i], dz[i], alpha[i],
                    alpha_z[i])))
        print('-'*len(header))


    return eta, dz

#%%
if __name__ == '__main__':
    p0 = 1000
    strat = False
    ztop = 15000
    # slope_t, intercept_t = 0.004, 296#0.004, 293
    # levels = np.arange(0, 12001, 20)
    # theta = xr.DataArray(dims=["level"], coords={"level" : levels})
    # theta["level"] = theta.level.assign_attrs(units="m")
    # theta = theta.level * slope_t + intercept_t
    # theta = theta.assign_attrs(units="K")
    # p = pressure_from_theta(theta, p0=p0)
    # p.interp(level=z)
   # eta, dz = create_levels(nz=160, ztop=12000, method=0, dz0=20, etaz1=0.87, etaz2=0.4, n2=37, theta=theta,p0=p0, plot=True, table=True, savefig=False)
   # eta, dz = create_levels(ztop=ztop, method=0, dz0=20, dzmax=200, p0=p0, savefig=True, strat=strat)
 #   eta, dz = create_levels(ztop=ztop, method=0, dz0=20, nz=120, p0=p0, savefig=True, strat=strat)
   # eta, dz = create_levels(ztop=ztop, dz0=20, method=3, nz=71, z1=20 , z2=2000, alpha=.5, theta=theta, p0=p0)
    #eta, dz = create_levels(ztop=ztop, dz0=20, dzmax=250, method=3, nz=120, D1=200, alpha=1., p0=p0, savefig=True)
  #  eta, dz = create_levels(ztop=ztop, dz0=20, method=3, nz=70, D1=0, alpha=1., p0=p0, savefig=True, strat=strat)
    eta, dz = create_levels(ztop=ztop, dz0=20, method=3, dzmax=400, D1=0, alpha=1., p0=p0, savefig=True, strat=strat)

    # eta, dz = create_levels(ztop=16000, dz0=50, method=3, nz=35, z1=200, z2=10000, alpha=1, theta=theta, p0=p0)
    print(', '.join(['%.6f'%eta_tmp for eta_tmp in eta]))
#%%

#%%
   # for eta_c in np.arange(0.1, 0.5, 0.1):
    fig, ax = plt.subplots(figsize=(5, 4))
    ax2 = ax.twiny()
    # axp = ax.twinx()

    ms = 3.
    alpha = np.diff(eta)[1:] / np.diff(eta)[:-1]
    pt = height_to_pressure_std(ztop, p0=p0, strat=strat)
    eta_c = .2
    zss = [1000, 0]
    symb = "o"
    for zs, mf in zip(zss, ["w", None]):
        ps = height_to_pressure_std(zs, p0=p0, strat=strat)
        z = height_from_eta(eta, eta_c, pt, ps, p0=p0, strat=strat)
        zc = height_from_eta(eta_c, eta_c, pt, ps, p0=p0, strat=strat)
        dz = np.diff(z)
        alpha_z = dz[1:] / dz[:-1]

        ax.plot(dz, z[:-1], symb, c='k', ms=ms, markerfacecolor=mf)
        ax.set_xlim(0, np.nanmax(dz)+20)
        ax.grid(c=(0.8, 0.8, 0.8))
        ax.set_ylabel('height (m)')
        ax.set_xlabel('$\Delta z$ (m)')

        ax2.plot(alpha_z, z[1:-1], symb, c="blue", ms=ms, markerfacecolor=mf)
        xlabel = r"\textcolor{blue}{$\Delta z (i)$/$\Delta z (i-1)$}, \textcolor{red}{$\Delta \eta (i)$/$\Delta \eta (i-1)$}"
        ax2.set_xlabel(xlabel)
        ax2.plot(alpha, z[1:-1], symb, c="red", ms=ms, markerfacecolor=mf)

       # p = height_to_pressure_std(z, p0=p0, strat=strat)

        # axp.plot(dz, p[:-1])
        # axp.set_yscale("log")
        # zlim = ax.get_ylim()
        # axp.set_ylim(1110, height_to_pressure_std(zlim[1], p0=p0, strat=strat))
        # axp.set_xlim(0, np.nanmax(dz)+20)
        # axp.set_ylabel("pressure (hPa)")
       # plt.title("$\eta_c=${}".format(eta_c))
    ax.hlines(zc, *ax.get_xlim(), colors="gray", linewidth=0.6)

    fig.savefig(figloc + '/wrf_stretched_grid_etaz.pdf', bbox_inches="tight")
