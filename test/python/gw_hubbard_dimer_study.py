################################################################################
#
# TPRF: Two-Particle Response Function (TPRF) Toolbox for TRIQS
#
# Copyright (C) 2023 by Hugo U.R. Strand
# Author: H. U.R. Strand
#
# TPRF is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# TPRF is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# TPRF. If not, see <http://www.gnu.org/licenses/>.
#
################################################################################

import sys
import itertools
import numpy as np

from triqs.lattice.tight_binding import TBLattice

from triqs.gf import Gf, MeshImFreq, Idx, inverse
from triqs.gf.gf_factories import make_gf_from_fourier

from triqs.operators import n, c, c_dag, Operator, dagger
from triqs_tprf.rpa_tensor import get_rpa_tensor
from triqs_tprf.gw import get_gw_tensor

from triqs_tprf.lattice import lattice_dyson_g_wk
from triqs_tprf.lattice import fourier_wk_to_wr
from triqs_tprf.lattice import chi_wr_from_chi_wk

from triqs_tprf.gw_solver import GWSolver


def get_ed_g(beta, t, U, wmesh):
    
    from pyed.TriqsExactDiagonalization import TriqsExactDiagonalization
    from triqs.operators import c, c_dag, n, Operator, dagger

    mu = U/2
    H = \
        -mu * (n('up',0) + n('do',0) + n('up',1) + n('do',1) ) + \
        U * n('up',0) * n('do',0) + \
        U * n('up',1) * n('do',1) + \
        -t * ( c_dag('up', 0) * c('up', 1) + c_dag('up', 1) * c('up', 0) ) + \
        -t * ( c_dag('do', 0) * c('do', 1) + c_dag('do', 1) * c('do', 0) )

    fundamental_operators = [ c('up', 0), c('do', 0), c('up', 1), c('do', 1) ]
    ed = TriqsExactDiagonalization(H, fundamental_operators, beta)

    G_w = Gf(mesh=wmesh, target_shape=[2,2])
    G_tau = make_gf_from_fourier(G_w)

    for i, j in itertools.product(range(2), repeat=2):
        ed.set_g2_tau(G_tau[i,j], c('up',i), c_dag('up',j) )
        
    G_w = make_gf_from_fourier(G_tau)

    return G_w


class EDHubbardDimer:

    def __init__(self, beta, t, U, wmesh):

        self.g_w = get_ed_g(beta, t, U, wmesh)
        self.g0_w = get_ed_g(beta, t, 0*U, wmesh)
        self.sigma_w = self.g_w.copy()
        self.sigma_w << inverse(self.g0_w) - inverse(self.g_w)


class GWHubbardDimerMatrix:

    def __init__(self, beta=20.0, U=1.5, t=1.0, mu=0.0, nw=1024, maxiter=100):

        wmesh = MeshImFreq(beta, 'Fermion', nw)
            
        tb_opts = dict(
            units = [(1, 0, 0)],
            orbital_positions = [(0,0,0)] * 4,
            orbital_names = ['up_0', 'do_0', 'up_1', 'do_1'],
            )

        H0 = np.array([
            [ 0,  0,  1,  0],
            [ 0,  0,  0,  1],
            [ 1,  0,  0,  0],
            [ 0,  1,  0,  0],
            ])

        H_r = TBLattice(hopping = {
            (0,): -t * H0,
            }, **tb_opts)

        kmesh = H_r.get_kmesh(n_k=(1, 1, 1))
        self.e_k = H_r.fourier(kmesh)

        self.H_int = U*n('up',0) * n('do',0) + U*n('up',1) * n('do',1)

        self.fundamental_operators = \
            [c('up', 0), c('do', 0), c('up', 1), c('do', 1)]

        self.V_aaaa = get_gw_tensor(self.H_int, self.fundamental_operators)
        
        self.V_k = Gf(mesh=kmesh, target_shape=[4]*4)
        self.V_k.data[:] = self.V_aaaa    

        gw = GWSolver(self.e_k, self.V_k, wmesh, mu=mu)
        gw.solve_iter(maxiter=maxiter, gw=True, hartree=False, fock=False)
        gw.calc_real_space()
        
        self.gw = gw

        for key, val in gw.__dict__.items():
            setattr(self, key, val)


class GWHubbardDimer:

    def __init__(
            self,
            beta=20.0, U=1.5, t=1.0, mu=0.0, nw=1024, maxiter=100,
            self_interaction=False):

        wmesh = MeshImFreq(beta, 'Fermion', nw)

        tb_opts = dict(
            units = [(1, 0, 0)],
            orbital_positions = [(0,0,0)] * 2,
            orbital_names = ['up_0', 'do_0'],
            )

        # Have to use t/2 hopping in the TBLattice since it considers
        # hoppings in both directions, which doubles the total hopping
        # for the Hubbard dimer.

        H_r = TBLattice(hopping = {
            (+1,): -0.5 * t * np.eye(2),
            (-1,): -0.5 * t * np.eye(2),
            }, **tb_opts)

        kmesh = H_r.get_kmesh(n_k=(2, 1, 1))
        self.e_k = H_r.fourier(kmesh)

        if self_interaction:
            V_aaaa = np.zeros((2, 2, 2, 2))

            V_aaaa[0, 0, 0, 0] = U
            V_aaaa[1, 1, 1, 1] = U
            
            V_aaaa[1, 1, 0, 0] = U
            V_aaaa[0, 0, 1, 1] = U

            self.V_aaaa = V_aaaa
            
        else:
            self.H_int = U * n('up',0) * n('do',0)
            self.fundamental_operators = [c('up', 0), c('do', 0)]
            self.V_aaaa = get_gw_tensor(self.H_int, self.fundamental_operators)
            
        
        self.V_k = Gf(mesh=kmesh, target_shape=[2]*4)
        self.V_k.data[:] = self.V_aaaa    

        gw = GWSolver(self.e_k, self.V_k, wmesh, mu=mu)
        gw.solve_iter(maxiter=maxiter, gw=True, hartree=False, fock=False)
        gw.calc_real_space()
        
        self.gw = gw

        for key, val in gw.__dict__.items():
            setattr(self, key, val)
        
        
def test_gw_hubbard_dimer_matrix(verbose=False):

    beta = 20.0
    U = 1.5
    t = 1.0
    mu = 0.0
    
    gw = GWHubbardDimerMatrix(
        beta = beta,
        U = U,
        t = t,
        mu = mu,
        nw = 1024,
        )

    wmesh = gw.g_wk.mesh[0]
    bmesh = gw.P_wk.mesh[0]
    kmesh = gw.P_wk.mesh[1]
    
    ed = EDHubbardDimer(beta, t, U, wmesh)
    
    W_wk_ref = gw.W_wk.copy()
    
    for k in kmesh:
        for w in bmesh:

            p = gw.P_wk[w, k][0,0,0,0]

            P_mat = np.array([
                [p, 0],
                [0, p]])

            V_mat = np.array([
                [0, U],
                [U, 0]])
            
            W_mat = np.linalg.inv(np.eye(2) - V_mat @ P_mat) @ V_mat

            denom = 1 - U**2 * p**2
            W_00 = U**2 * p / denom
            W_01 = U / denom

            np.testing.assert_array_almost_equal(W_00, W_mat[0,0])
            np.testing.assert_array_almost_equal(W_01, W_mat[0,1])

            W_wk_ref[w, k][0,0,0,0] = W_mat[0,0]
            W_wk_ref[w, k][1,1,1,1] = W_mat[1,1]
            W_wk_ref[w, k][0,0,1,1] = W_mat[0,1]
            W_wk_ref[w, k][1,1,0,0] = W_mat[1,0]
            
    W_wr_ref = chi_wr_from_chi_wk(W_wk_ref)

    #np.testing.assert_array_almost_equal(W_wr_ref.data, W_wr.data)
    
    print(f'g0_wr0 =\n{gw.g0_wr[Idx(0), Idx(0, 0, 0)].real}')
    print(f'g_wr0 =\n{gw.g_wr[Idx(0), Idx(0, 0, 0)].real}')

    print('V_aaaa =')
    print_tensor(gw.V_aaaa)

    print('V_wr0')
    print_tensor(gw.V_wr[Idx(0), Idx(0, 0, 0)])

    print('P_wr0')
    print_tensor(gw.P_wr[Idx(0), Idx(0, 0, 0)])

    print('W_wr0')
    print_tensor(gw.W_wr[Idx(0), Idx(0, 0, 0)])
    
    #i,j,k,l = 0,0,0,0
    i,j,k,l = 0,0,1,1
    #i,j,k,l = 1,0,0,1        

    # -- Analytic expression Eq. (18) for G_0

    g0_0_w = Gf(mesh=wmesh, target_shape=[])
    g0_1_w = Gf(mesh=wmesh, target_shape=[])
    
    for w in wmesh:
        g0_0_w[w] = +0.5/(w - t) + 0.5/(w + t)
        g0_1_w[w] = -0.5/(w - t) + 0.5/(w + t)

    #np.testing.assert_array_almost_equal(
    #    g0_wr[:, Idx(0, 0, 0)][0, 0].data, g0_0_w.data)

    #np.testing.assert_array_almost_equal(
    #    g0_wr[:, Idx(1, 0, 0)][0, 0].data, g0_1_w.data)
    
    # -- Analytic expression Eq. (29) for P

    P_0_w = Gf(mesh=bmesh, target_shape=[])
    P_1_w = Gf(mesh=bmesh, target_shape=[])

    for w in bmesh:
        P_0_w[w] = + 0.25 / (w - 2*t) - 0.25 / (w + 2*t)
        P_1_w[w] = - 0.25 / (w - 2*t) + 0.25 / (w + 2*t)
        
    #np.testing.assert_array_almost_equal(
    #    P_wr[:, Idx(0, 0, 0)][0,0,0,0].data, P_0_w.data)

    #np.testing.assert_array_almost_equal(
    #    P_wr[:, Idx(1, 0, 0)][0,0,0,0].data, P_1_w.data)

    # -- Analytic expression Eq. (30) for W

    W_0_w = Gf(mesh=bmesh, target_shape=[])
    W_1_w = Gf(mesh=bmesh, target_shape=[])

    e = 0.0
    h2 = 4*t**2 + 4*U*t # Eq. in text after Eq. (31)    
    h = np.sqrt(h2)

    for w in bmesh:
        W_0_w[w] = U + 2 * U**2 * t / (complex(w)**2 - h2)
        W_1_w[w] = 0 - 2 * U**2 * t / (complex(w)**2 - h2)
        
    #np.testing.assert_array_almost_equal(
    #    W_wr[:, Idx(0, 0, 0)][i,j,k,l].data, W_0_w.data)

    #np.testing.assert_array_almost_equal(
    #    W_wr[:, Idx(1, 0, 0)][i,j,k,l].data, W_1_w.data)

    # Analytic expression in Eq. (31) for Sigma = G_0 W_0
    
    sigma_0_w = Gf(mesh=wmesh, target_shape=[])
    sigma_1_w = Gf(mesh=wmesh, target_shape=[])

    for w in wmesh:
        sigma_0_w[w] = U/2 + U**2 * t / (2*h) * \
            ( 1/(w - (e + t + h)) + 1/(w - (e - t - h)) )
        sigma_1_w[w] = U**2 * t / (2*h) * \
            ( 1/(w - (e + t + h)) - 1/(w - (e - t - h)) )
        
    #np.testing.assert_array_almost_equal(
    #    sigma_wr[:, Idx(0, 0, 0)][0, 0].data, sigma_0_w.data)

    #np.testing.assert_array_almost_equal(
    #    sigma_wr[:, Idx(1, 0, 0)][0, 0].data, sigma_1_w.data)
        
    # -- Analytic expression Eq. (32) for G = 1/[1/G_0 - Sigma] with Sigma = G_0 W_0
    
    g_0_w = Gf(mesh=wmesh, target_shape=[])
    g_1_w = Gf(mesh=wmesh, target_shape=[])

    q = 0.0
    
    A = np.sqrt((2*t + h + q*U/2)**2 + 4*U**2*t/h)
    B = np.sqrt((2*t + h - q*U/2)**2 + 4*U**2*t/h)

    w1_p = 0.5 * (2*e - h + q*U/2 + A)
    w1_m = 0.5 * (2*e - h + q*U/2 - A)

    w2_p = 0.5 * (2*e + h + q*U/2 + B)
    w2_m = 0.5 * (2*e + h + q*U/2 - B)
    
    #A = np.sqrt((h + 2*t)**2 + 2*U**2*t/h)
    #B = np.sqrt((h - 2*t - U/2)**2 + 2*U**2*t/h)
    #C = np.sqrt((h + 2*t - U/2)**2 + 2*U**2*t/h)

    #w1_p = (2*e - h + A)/2
    #w1_m = (2*e - h - A)/2

    #w2_p = (2*e + h + A)/2
    #w2_m = (2*e + h - A)/2

    #w3_p = (2*e + h + U/2 + B/2)
    #w3_m = (2*e + h + U/2 - B/2)

    #w4_p = (2*e + h + U/2 + C)/2
    #w4_m = (2*e + h + U/2 - C)/2

    R1 = (h + 2*t + q*U/2) / (4 * A)
    R2 = (-h -2*t + q*U/2) / (4 * B)

    #print(f'A = {A}')
    #print(f'B = {B}')
    #print(f'w1_p = {w1_p}')
    #print(f'w1_m = {w1_m}')
    #print(f'w2_p = {w2_p}')
    #print(f'w2_m = {w2_m}')
    
    for w in wmesh:
        g_0_w[w] = \
            + (0.25 + R1)/(w - w1_p) + (0.25 - R1)/(w - w1_m) + \
            + (0.25 + R2)/(w - w2_p) + (0.25 - R2)/(w - w2_m)
        g_1_w[w] = \
            - (0.25 + R1)/(w - w1_p) - (0.25 - R1)/(w - w1_m) + \
            + (0.25 + R2)/(w - w2_p) + (0.25 - R2)/(w - w2_m)

    #np.testing.assert_array_almost_equal(
    #    g_wr[:, Idx(0, 0, 0)][0, 0].data, g_0_w.data)

    #np.testing.assert_array_almost_equal(
    #    g_wr[:, Idx(1, 0, 0)][0, 0].data, g_1_w.data)

    
    if verbose:
        from triqs.plot.mpl_interface import oplot, oploti, oplotr, plt

        plt.figure(figsize=(13, 9))

        subp = [3, 4, 1]
        xlim = [-10, 10]

        def plot_cf(g_tprf, g_ref, subp, plot=oploti):
            plt.subplot(*subp); subp[-1] += 1
            plot(g_ref, 'g.', label='ref')
            plot(g_tprf, 'c-', label='tprf')
            plt.xlim(xlim)


        plot_cf(gw.g0_wr[:, Idx(0, 0, 0)][0, 0], g0_0_w, subp, plot=oploti)
        plt.ylabel(r'$G^{(0)}_{00}$')

        plot_cf(gw.g0_wr[:, Idx(0, 0, 0)][0, 2], g0_1_w, subp, plot=oplotr)
        plt.ylabel(r'$G^{(0)}_{02}$')
        
        #plot_cf(g0_wr[:, Idx(1, 0, 0)][0, 0], g0_1_w, subp, plot=oplotr)
        #plt.ylabel(r'$G_0(r=1)$')

        plot_cf(gw.P_wr[:, Idx(0, 0, 0)][0,0,0,0], P_0_w, subp, plot=oplotr)
        plt.ylabel(r'$P_{0000}$')

        plot_cf(gw.P_wr[:, Idx(0, 0, 0)][0,0,2,2], P_1_w, subp, plot=oplotr)
        plt.ylabel(r'$P_{0022}$')
        
        #plot_cf(P_wr[:, Idx(1, 0, 0)][0,0,0,0], P_1_w, subp, plot=oplotr)
        #plt.ylabel(r'$P(r=1)$')

        i,j,k,l = 0,0,0,0

        plot_cf(gw.W_wr[:, Idx(0, 0, 0)][i,j,k,l], W_0_w, subp, plot=oplot)
        #oplot(W_wr_ref[:, Idx(0, 0, 0)][i,j,k,l], 'r--', label='W ref')
        plt.ylabel(r'$W(r=0)$')            
        plt.title(f'{i},{j},{k},{l}')

        #plot_cf(W_wr[:, Idx(1, 0, 0)][i,j,k,l], W_1_w, subp, plot=oplot)
        #oplot(W_wr_ref[:, Idx(1, 0, 0)][i,j,k,l], 'r--', label='W ref')
        #plt.ylabel(r'$W(r=1)$')
        #plt.title(f'{i},{j},{k},{l}')

        i,j,k,l = 0,0,1,1

        plot_cf(gw.W_wr[:, Idx(0, 0, 0)][i,j,k,l], W_0_w, subp, plot=oplot)
        #oplot(W_wr_ref[:, Idx(0, 0, 0)][i,j,k,l], 'r--', label='W ref')
        plt.ylabel(r'$W(r=0)$')            
        plt.title(f'{i},{j},{k},{l}')

        i,j,k,l = 0,0,2,2

        plot_cf(gw.W_wr[:, Idx(0, 0, 0)][i,j,k,l], W_0_w, subp, plot=oplot)
        #oplot(W_wr_ref[:, Idx(0, 0, 0)][i,j,k,l], 'r--', label='W ref')
        plt.ylabel(r'$W(r=0)$')            
        plt.title(f'{i},{j},{k},{l}')

        i,j,k,l = 0,0,3,3

        plot_cf(gw.W_wr[:, Idx(0, 0, 0)][i,j,k,l], W_0_w, subp, plot=oplot)
        #oplot(W_wr_ref[:, Idx(0, 0, 0)][i,j,k,l], 'r--', label='W ref')
        plt.ylabel(r'$W(r=0)$')            
        plt.title(f'{i},{j},{k},{l}')
        
        #plot_cf(W_wr[:, Idx(1, 0, 0)][i,j,k,l], W_1_w, subp, plot=oplot)
        #oplot(W_wr_ref[:, Idx(1, 0, 0)][i,j,k,l], 'r--', label='W ref')
        #plt.ylabel(r'$W(r=1)$')
        #plt.title(f'{i},{j},{k},{l}')

        plot_cf(gw.sigma_wr[:, Idx(0, 0, 0)][0, 0], sigma_0_w, subp, plot=oplot)
        #oplot(sigma_wr_ref[:, Idx(0, 0, 0)][0, 0], 'r--', label='sigma ref')
        plt.ylabel(r'$\Sigma(r=0)$')

        plot_cf(gw.sigma_wr[:, Idx(0, 0, 0)][0, 2], sigma_1_w, subp, plot=oplot)
        #oplot(sigma_wr_ref[:, Idx(0, 0, 0)][0, 0], 'r--', label='sigma ref')
        plt.ylabel(r'$\Sigma(r=1)$')
        
        #plot_cf(sigma_wr[:, Idx(1, 0, 0)][0, 0], sigma_1_w, subp, plot=oplot)
        ##oplot(sigma_wr_ref[:, Idx(1, 0, 0)][0, 0], 'r--', label='sigma ref')
        #plt.ylabel(r'$\Sigma(r=1)$')
            

        plt.subplot(*subp); subp[-1] += 1
        oplot(g_0_w, 'g.', label='ref')
        oploti(gw.g0_wr[:, Idx(0, 0, 0)][0, 0], 'r-', label='tprf g0')
        oplot(gw.g_wr[:, Idx(0, 0, 0)][0, 0], 'c-', label='tprf g')
        oplot(ed.g_w[0, 0], 'b--', label='ed g')
        plt.xlim(xlim)
        plt.ylabel(r'$G(r=0)$')

        plt.subplot(*subp); subp[-1] += 1
        oplot(g_1_w, 'g.', label='ref')
        oplotr(gw.g0_wr[:, Idx(0, 0, 0)][0, 2], 'r-', label='tprf g0')
        oplot(gw.g_wr[:, Idx(0, 0, 0)][0, 2], 'c-', label='tprf g')
        oplot(ed.g_w[0, 1], 'b--', label='ed g')
        plt.xlim(xlim)
        plt.ylabel(r'$G(r=1)$')
        
        #plt.subplot(*subp); subp[-1] += 1
        #oplot(g_1_w, 'g.')
        #oplot(g_wr[:, Idx(1, 0, 0)][0, 0], 'c-', label='tprf g')
        #oplotr(g0_wr[:, Idx(1, 0, 0)][0, 0], 'r-', label='tprf g0')
        #oplot(-g_w_ed[0, 1], 'b--', label='ed g')
        #plt.xlim(xlim)
        #plt.ylabel(r'$G(r=1)$')


        plt.tight_layout()
        plt.show()
    

def test_gw_hubbard_dimer_sic(verbose=False):

    """
    SELF INTERACTION CORRECTED GW on the Hubbard dimer... WIP
    
    Comparing to analytical expressions from:
    Chapter 4: Hubbard Dimer in GW and Beyond, by Pina Romaniello

    In the book:
    Simulating Correlations with Computers - Modeling and Simulation Vol. 11
    E. Pavarini and E. Koch (eds.)
    Forschungszentrum Ju ̈lich, 2021, ISBN 978-3-95806-529-1
    
    https://www.cond-mat.de/events/correl21/manuscripts/correl21.pdf    
    """
    
    beta = 20.0
    U = 1.5
    t = 1.0
    nw = 1024
    mu = 0.0

    gw = GWHubbardDimer(
        beta = beta,
        U = U,
        t = t,
        mu = mu,
        nw = 1024,
        maxiter = 1,
        self_interaction=True,
        )
    
    wmesh = gw.g_wk.mesh[0]
    bmesh = gw.P_wk.mesh[0]
    kmesh = gw.P_wk.mesh[1]

    g_w_ed = get_ed_g(beta, t, U, wmesh)
    
    print(f'g_wr0 =\n{gw.g_wr[Idx(0), Idx(0, 0, 0)]}')
    print(f'g_wr1 =\n{gw.g_wr[Idx(0), Idx(1, 0, 0)]}')

    print('V_aaaa =')
    print_tensor(gw.V_aaaa)

    print('V_wr0')
    print_tensor(gw.V_wr[Idx(0), Idx(0, 0, 0)])
    print('V_wr1')
    print_tensor(gw.V_wr[Idx(0), Idx(1, 0, 0)])

    print('P_wr0')
    print_tensor(gw.P_wr[Idx(0), Idx(0, 0, 0)])
    print('P_wr1')
    print_tensor(gw.P_wr[Idx(0), Idx(1, 0, 0)])

    print('W_wr0')
    print_tensor(gw.W_wr[Idx(0), Idx(0, 0, 0)])
    print('W_wr1')
    print_tensor(gw.W_wr[Idx(0), Idx(1, 0, 0)])

    #i,j,k,l = 0,0,0,0
    i,j,k,l = 0,0,1,1
    #i,j,k,l = 1,0,0,1        

    # -- Analytic expression Eq. (18) for G_0

    g0_0_w = Gf(mesh=wmesh, target_shape=[])
    g0_1_w = Gf(mesh=wmesh, target_shape=[])
    
    for w in wmesh:
        g0_0_w[w] = +0.5/(w - t) + 0.5/(w + t)
        g0_1_w[w] = -0.5/(w - t) + 0.5/(w + t)

    np.testing.assert_array_almost_equal(
        gw.g0_wr[:, Idx(0, 0, 0)][0, 0].data, g0_0_w.data)

    np.testing.assert_array_almost_equal(
        gw.g0_wr[:, Idx(1, 0, 0)][0, 0].data, g0_1_w.data)
    
    # -- Analytic expression Eq. (29) for P

    P_0_w = Gf(mesh=bmesh, target_shape=[])
    P_1_w = Gf(mesh=bmesh, target_shape=[])

    for w in bmesh:
        P_0_w[w] = + 0.25 / (w - 2*t) - 0.25 / (w + 2*t)
        P_1_w[w] = - 0.25 / (w - 2*t) + 0.25 / (w + 2*t)
        
    np.testing.assert_array_almost_equal(
        gw.P_wr[:, Idx(0, 0, 0)][0,0,0,0].data, P_0_w.data)

    np.testing.assert_array_almost_equal(
        gw.P_wr[:, Idx(1, 0, 0)][0,0,0,0].data, P_1_w.data)

    # -- Analytic expression Eq. (30) for W

    W_0_w = Gf(mesh=bmesh, target_shape=[])
    W_1_w = Gf(mesh=bmesh, target_shape=[])

    e = 0.0
    h2 = 4*t**2 + 4*U*t # Eq. in text after Eq. (31)    
    h = np.sqrt(h2)

    for w in bmesh:
        W_0_w[w] = U + 2 * U**2 * t / (complex(w)**2 - h2)
        W_1_w[w] = 0 - 2 * U**2 * t / (complex(w)**2 - h2)
        
    np.testing.assert_array_almost_equal(
        gw.W_wr[:, Idx(0, 0, 0)][i,j,k,l].data, W_0_w.data)

    np.testing.assert_array_almost_equal(
        gw.W_wr[:, Idx(1, 0, 0)][i,j,k,l].data, W_1_w.data)

    # Analytic expression in Eq. (31) for Sigma = G_0 W_0
    
    sigma_0_w = Gf(mesh=wmesh, target_shape=[])
    sigma_1_w = Gf(mesh=wmesh, target_shape=[])

    for w in wmesh:
        sigma_0_w[w] = U/2 + U**2 * t / (2*h) * \
            ( 1/(w - (e + t + h)) + 1/(w - (e - t - h)) )
        sigma_1_w[w] = U**2 * t / (2*h) * \
            ( 1/(w - (e + t + h)) - 1/(w - (e - t - h)) )
        
    np.testing.assert_array_almost_equal(
        gw.sigma_wr[:, Idx(0, 0, 0)][0, 0].data + U/2, sigma_0_w.data)

    np.testing.assert_array_almost_equal(
        gw.sigma_wr[:, Idx(1, 0, 0)][0, 0].data, sigma_1_w.data)
        
    # -- Analytic expression Eq. (32) for G = 1/[1/G_0 - Sigma] with Sigma = G_0 W_0
    
    g_0_w = Gf(mesh=wmesh, target_shape=[])
    g_1_w = Gf(mesh=wmesh, target_shape=[])

    q = 0.0
    
    A = np.sqrt((2*t + h + q*U/2)**2 + 4*U**2*t/h)
    B = np.sqrt((2*t + h - q*U/2)**2 + 4*U**2*t/h)

    w1_p = 0.5 * (2*e - h + q*U/2 + A)
    w1_m = 0.5 * (2*e - h + q*U/2 - A)

    w2_p = 0.5 * (2*e + h + q*U/2 + B)
    w2_m = 0.5 * (2*e + h + q*U/2 - B)
    
    #A = np.sqrt((h + 2*t)**2 + 2*U**2*t/h)
    #B = np.sqrt((h - 2*t - U/2)**2 + 2*U**2*t/h)
    #C = np.sqrt((h + 2*t - U/2)**2 + 2*U**2*t/h)

    #w1_p = (2*e - h + A)/2
    #w1_m = (2*e - h - A)/2

    #w2_p = (2*e + h + A)/2
    #w2_m = (2*e + h - A)/2

    #w3_p = (2*e + h + U/2 + B/2)
    #w3_m = (2*e + h + U/2 - B/2)

    #w4_p = (2*e + h + U/2 + C)/2
    #w4_m = (2*e + h + U/2 - C)/2

    R1 = (h + 2*t + q*U/2) / (4 * A)
    R2 = (-h -2*t + q*U/2) / (4 * B)

    #print(f'A = {A}')
    #print(f'B = {B}')
    #print(f'w1_p = {w1_p}')
    #print(f'w1_m = {w1_m}')
    #print(f'w2_p = {w2_p}')
    #print(f'w2_m = {w2_m}')
    
    for w in wmesh:
        g_0_w[w] = \
            + (0.25 + R1)/(w - w1_p) + (0.25 - R1)/(w - w1_m) + \
            + (0.25 + R2)/(w - w2_p) + (0.25 - R2)/(w - w2_m)
        g_1_w[w] = \
            - (0.25 + R1)/(w - w1_p) - (0.25 - R1)/(w - w1_m) + \
            + (0.25 + R2)/(w - w2_p) + (0.25 - R2)/(w - w2_m)

    np.testing.assert_array_almost_equal(
        gw.g_wr[:, Idx(0, 0, 0)][0, 0].data, g_0_w.data)

    np.testing.assert_array_almost_equal(
        gw.g_wr[:, Idx(1, 0, 0)][0, 0].data, g_1_w.data)

    
    if verbose:
        from triqs.plot.mpl_interface import oplot, oploti, oplotr, plt

        plt.figure(figsize=(13, 9))

        subp = [3, 4, 1]
        xlim = [-10, 10]

        def plot_cf(g_tprf, g_ref, subp, plot=oploti):
            plt.subplot(*subp); subp[-1] += 1
            plot(g_ref, 'g.', label='ref')
            plot(g_tprf, 'c-', label='tprf')
            plt.xlim(xlim)


        plot_cf(gw.g0_wr[:, Idx(0, 0, 0)][0, 0], g0_0_w, subp, plot=oploti)
        plt.ylabel(r'$G_0(r=0)$')

        plot_cf(gw.g0_wr[:, Idx(1, 0, 0)][0, 0], g0_1_w, subp, plot=oplotr)
        plt.ylabel(r'$G_0(r=1)$')

        plot_cf(gw.P_wr[:, Idx(0, 0, 0)][0,0,0,0], P_0_w, subp, plot=oplotr)
        plt.ylabel(r'$P(r=0)$')

        plot_cf(gw.P_wr[:, Idx(1, 0, 0)][0,0,0,0], P_1_w, subp, plot=oplotr)
        plt.ylabel(r'$P(r=1)$')

        i,j,k,l = 0,0,0,0

        plot_cf(gw.W_wr[:, Idx(0, 0, 0)][i,j,k,l], W_0_w, subp, plot=oplot)
        plt.ylabel(r'$W(r=0)$')            
        plt.title(f'{i},{j},{k},{l}')

        plot_cf(gw.W_wr[:, Idx(1, 0, 0)][i,j,k,l], W_1_w, subp, plot=oplot)
        plt.ylabel(r'$W(r=1)$')
        plt.title(f'{i},{j},{k},{l}')

        i,j,k,l = 0,0,1,1

        plot_cf(gw.W_wr[:, Idx(0, 0, 0)][i,j,k,l], W_0_w, subp, plot=oplot)
        plt.ylabel(r'$W(r=0)$')            
        plt.title(f'{i},{j},{k},{l}')

        plot_cf(gw.W_wr[:, Idx(1, 0, 0)][i,j,k,l], W_1_w, subp, plot=oplot)
        plt.ylabel(r'$W(r=1)$')
        plt.title(f'{i},{j},{k},{l}')

        plot_cf(gw.sigma_wr[:, Idx(0, 0, 0)][0, 0], sigma_0_w, subp, plot=oplot)
        plt.ylabel(r'$\Sigma(r=0)$')

        plot_cf(gw.sigma_wr[:, Idx(1, 0, 0)][0, 0], sigma_1_w, subp, plot=oplot)
        plt.ylabel(r'$\Sigma(r=1)$')
            

        plt.subplot(*subp); subp[-1] += 1
        oplot(g_0_w, 'g.', label='ref')
        oplot(gw.g_wr[:, Idx(0, 0, 0)][0, 0], 'c-', label='tprf g')
        oploti(gw.g0_wr[:, Idx(0, 0, 0)][0, 0], 'r-', label='tprf g0')
        oplot(g_w_ed[0, 0], 'b--', label='ed g')
        plt.xlim(xlim)
        plt.ylabel(r'$G(r=0)$')
            
        plt.subplot(*subp); subp[-1] += 1
        oplot(g_1_w, 'g.')
        oplot(gw.g_wr[:, Idx(1, 0, 0)][0, 0], 'c-', label='tprf g')
        oplotr(gw.g0_wr[:, Idx(1, 0, 0)][0, 0], 'r-', label='tprf g0')
        oplot(g_w_ed[0, 1], 'b--', label='ed g')
        plt.xlim(xlim)
        plt.ylabel(r'$G(r=1)$')


        plt.tight_layout()
        plt.show()
        

def print_tensor(U, tol=1e-9):
    assert( len(U.shape) == 4)
    n = U.shape[0]
    
    import itertools
    for i,j,k,l in itertools.product(range(n), repeat=4):
        value = U[i, j, k, l]
        if np.abs(value) > tol:
            print(f'{i}, {j}, {k}, {l} -- {value}')


def compare_gw_solutions():

    beta = 40.0
    U = 1.5
    t = 1.0
    mu = 0.0
    nw = 1024 * 2

    opts = dict(beta=beta, U=U, t=t, mu=mu, nw=nw)

    g0w0     = GWHubbardDimer(maxiter=1, self_interaction=True,  **opts)
    g0w0_sic = GWHubbardDimer(maxiter=1, self_interaction=False, **opts)
    
    gw     = GWHubbardDimer(maxiter=100, self_interaction=True,  **opts)
    gw_sic = GWHubbardDimer(maxiter=100, self_interaction=False, **opts)
    
    ed = EDHubbardDimer(beta, t, U, gw.g_wk.mesh[0])
    
    from triqs.plot.mpl_interface import oplot, oploti, oplotr, plt
    
    plt.figure(figsize=(8, 5))

    subp = [2, 2, 1]
    xlim = [0, 10]

    plt.subplot(*subp); subp[-1] += 1
    oploti(ed.g_w[0, 0], label='ED')
    oploti(g0w0.g_wr[:, Idx(0, 0, 0)][0, 0], '--', label='G0W0 spin-sum')
    oploti(g0w0_sic.g_wr[:, Idx(0, 0, 0)][0, 0], '--', label='G0W0 SIC')
    oploti(gw.g0_wr[:, Idx(0, 0, 0)][0, 0], '-', label='G_0')
    plt.xlim(xlim)
    plt.ylim(top=0)
    plt.ylabel(r'$G(r=0)$')

    plt.subplot(*subp); subp[-1] += 1
    oploti(ed.g_w[0, 0], label='ED')
    oploti(gw.g_wr[:, Idx(0, 0, 0)][0, 0], '--', label='scGW spin-sum')
    oploti(gw_sic.g_wr[:, Idx(0, 0, 0)][0, 0], '--', label='scGW SIC')
    oploti(gw.g0_wr[:, Idx(0, 0, 0)][0, 0], '-', label='G_0')
    plt.xlim(xlim)
    plt.ylim(top=0)
    plt.ylabel(r'$G(r=0)$')

    plt.subplot(*subp); subp[-1] += 1
    oploti(ed.sigma_w[0, 0], label='ED')
    oploti(g0w0.sigma_wr[:, Idx(0, 0, 0)][0, 0], '--', label='G0W0 spin-sum')
    oploti(g0w0_sic.sigma_wr[:, Idx(0, 0, 0)][0, 0], '--', label='G0W0 SIC')
    plt.xlim(xlim)
    plt.ylim(top=0)
    plt.ylabel(r'$\Sigma(r=0)$')

    plt.subplot(*subp); subp[-1] += 1
    oploti(ed.sigma_w[0, 0], label='ED')
    oploti(gw.sigma_wr[:, Idx(0, 0, 0)][0, 0], '--', label='scGW spin-sum')
    oploti(gw_sic.sigma_wr[:, Idx(0, 0, 0)][0, 0], '--', label='scGW SIC')
    plt.xlim(xlim)
    plt.ylim(top=0)
    plt.ylabel(r'$\Sigma(r=0)$')
    
    plt.tight_layout()
    plt.savefig('figure_gw_hubbard_dimer_cf_G0W0_and_scGW_SIC_vs_spinsum.pdf')
    plt.show()

        
if __name__ == '__main__':

    #test_gw_hubbard_dimer_sic(verbose=True)
    #test_gw_hubbard_dimer_matrix(verbose=True)

    compare_gw_solutions()