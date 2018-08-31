/*******************************************************************************
 *
 * TRIQS: a Toolbox for Research in Interacting Quantum Systems
 *
 * Copyright (C) 2017, H. U.R. Strand
 *
 * TRIQS is free software: you can redistribute it and/or modify it under the
 * terms of the GNU General Public License as published by the Free Software
 * Foundation, either version 3 of the License, or (at your option) any later
 * version.
 *
 * TRIQS is distributed in the hope that it will be useful, but WITHOUT ANY
 * WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
 * FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
 * details.
 *
 * You should have received a copy of the GNU General Public License along with
 * TRIQS. If not, see <http://www.gnu.org/licenses/>.
 *
 ******************************************************************************/

#include <triqs/utility/timer.hpp>

#include "../linalg.hpp"
#include "../mpi.hpp"

#include "chi_imfreq.hpp"
#include "common.hpp"

namespace tprf {

// ----------------------------------------------------
// chi0 bubble in Matsubara frequency

/*
chi0r_t chi0r_from_gr_PH(int nw, int nnu, gr_iw_vt gr) {

int nb = gr.target().shape()[0];
auto clmesh = std::get<1>(gr.mesh());
double beta = std::get<0>(gr.mesh()).domain().beta;

chi0r_t chi0r{{{beta, Boson, nw}, {beta, Fermion, nnu}, clmesh},
              {nb, nb, nb, nb}};

chi0r(iw, inu, r)(a, b, c, d)
    << -beta * gr(inu, r)(d, a) * gr(inu + iw, -r)(b, c);

return chi0r;
}
*/

chi0r_t chi0r_from_gr_PH(int nw, int nnu, gr_iw_vt g_nr) {

  auto _ = all_t{};

  int nb = g_nr.target().shape()[0];
  auto rmesh = std::get<1>(g_nr.mesh());

  double beta = std::get<0>(g_nr.mesh()).domain().beta;

  auto wmesh = gf_mesh<imfreq>{beta, Boson, nw};
  auto nmesh = gf_mesh<imfreq>{beta, Fermion, nnu};

  chi0r_t chi0_wnr{{wmesh, nmesh, rmesh}, {nb, nb, nb, nb}};

  auto g_target = g_nr.target();
  auto chi_target = chi0_wnr.target();

  auto arr = mpi_view(rmesh);

#pragma omp parallel for
  for (int idx = 0; idx < arr.size(); idx++) {
    auto &r = arr(idx);

    auto chi0_wn =
        make_gf<cartesian_product<imfreq, imfreq>>({wmesh, nmesh}, chi_target);
    auto g_pr_n = make_gf<imfreq>(nmesh, g_target);
    auto g_mr_n = make_gf<imfreq>(nmesh, g_target);

#pragma omp critical
    {
      g_pr_n = g_nr[_, r];
      g_mr_n = g_nr[_, -r];
    }

    for (auto const &w : wmesh)
      for (auto const &n : nmesh)
        chi0_wn[w, n](a, b, c, d)
            << -beta * g_pr_n(n)(d, a) * g_mr_n(n + w)(b, c);

#pragma omp critical
    chi0_wnr[_, _, r] = chi0_wn;

    // chi0r(iw, inu, r)(a, b, c, d) << -beta * gr(inu, r)(d, a) * gr(inu + iw,
    // -r)(b, c);
  }

  chi0_wnr = mpi_all_reduce(chi0_wnr);
  return chi0_wnr;
}

// ----------------------------------------------------

gf<imfreq, tensor_valued<4>> chi0_n_from_g_wk_PH(mesh_point<gf_mesh<imfreq>> w,
                                                 mesh_point<cluster_mesh> q,
                                                 gf_mesh<imfreq> fmesh,
                                                 gk_iw_vt g_wk) {

  int nb = g_wk.target().shape()[0];
  auto [fmesh_large, kmesh] = g_wk.mesh();

  double beta = fmesh.domain().beta;

  gf<imfreq, tensor_valued<4>> chi0_n{fmesh, {nb, nb, nb, nb}};

  // 100x times slower
  // chi0_n(inu)(a, b, c, d) << -beta/kmesh.size() * sum(g_wk(inu, k)(d, a) *
  // g_wk(inu + w, k - q)(b, c), k=kmesh);

  for (auto const &n : fmesh) {
    for (auto const &k : kmesh) {
      auto g_da = g_wk[n, k];
      auto g_bc = g_wk[n + w, k - q];
      for (auto a : range(nb))
        for (auto b : range(nb))
          for (auto c : range(nb))
            for (auto d : range(nb))
              chi0_n[n](a, b, c, d) -= g_da(d, a) * g_bc(b, c);
    }
  }

  chi0_n *= beta / kmesh.size();

  return chi0_n;
}

gf<imfreq, tensor_valued<4>>
chi0_n_from_e_k_sigma_w_PH(mesh_point<gf_mesh<imfreq>> w,
                           mesh_point<cluster_mesh> q, gf_mesh<imfreq> fmesh,
                           double mu, ek_vt e_k, g_iw_vt sigma_w) {

  int nb = e_k.target().shape()[0];
  auto kmesh = e_k.mesh();

  auto fmesh_large = sigma_w.mesh();

  double beta = fmesh.domain().beta;
  auto I = make_unit_matrix<ek_vt::scalar_t>(e_k.target_shape()[0]);

  gf<imfreq, tensor_valued<4>> chi0_n{fmesh, {nb, nb, nb, nb}};

  for (auto const &k : kmesh) {
    for (auto const &n : fmesh) {

      auto g_da = inverse((n + mu) * I - e_k[k] - sigma_w[matsubara_freq(n)]);
      auto g_bc = inverse((n + mu) * I - e_k[k - q] - sigma_w[n + w]);

      for (auto a : range(nb))
        for (auto b : range(nb))
          for (auto c : range(nb))
            for (auto d : range(nb))
              chi0_n[n](a, b, c, d) -= g_da(d, a) * g_bc(b, c);
    }
  }

  chi0_n *= beta / kmesh.size();

  return chi0_n;
}

chi0q_t chi0q_from_g_wk_PH(int nw, int nnu, gk_iw_vt g_wk) {

  auto [fmesh_large, kmesh] = g_wk.mesh();

  int nb = g_wk.target().shape()[0];
  double beta = std::get<0>(g_wk.mesh()).domain().beta;

  gf_mesh<imfreq> bmesh{beta, Boson, nw};
  gf_mesh<imfreq> fmesh{beta, Fermion, nnu};

  assert(fmesh.size() < fmesh_large.size());

  chi0q_t chi0_wnk({bmesh, fmesh, kmesh}, {nb, nb, nb, nb});

  auto _ = all_t{};
  for (auto const &[w, q] : gf_mesh{bmesh, kmesh}) {
    chi0_wnk[w, _, q] = chi0_n_from_g_wk_PH(w, q, fmesh, g_wk);
  }

  return chi0_wnk;
}

chi0r_t chi0r_from_chi0q(chi0q_vt chi0_wnk) {

  auto [bmesh, fmesh, kmesh] = chi0_wnk.mesh();
  auto rmesh = make_adjoint_mesh(kmesh);

  auto chi0_wnr =
      make_gf<chi0r_t::mesh_t::var_t>({bmesh, fmesh, rmesh}, chi0_wnk.target());

  auto _ = all_t{};
  for (auto const &[w, n] : mpi_view(gf_mesh{bmesh, fmesh}))
    chi0_wnr[w, n, _] = fourier(chi0_wnk[w, n, _]);
  chi0_wnr = mpi_all_reduce(chi0_wnr);

  return chi0_wnr;
}

chi0q_t chi0q_from_chi0r(chi0r_vt chi0_wnr) {

  auto [bmesh, fmesh, rmesh] = chi0_wnr.mesh();
  auto kmesh = make_adjoint_mesh(rmesh);

  auto chi0_wnk =
      make_gf<chi0q_t::mesh_t::var_t>({bmesh, fmesh, kmesh}, chi0_wnr.target());

  auto _ = all_t{};
  for (auto const &[w, n] : mpi_view(gf_mesh{bmesh, fmesh}))
    chi0_wnk[w, n, _] = fourier(chi0_wnr[w, n, _]);
  chi0_wnk = mpi_all_reduce(chi0_wnk);

  return chi0_wnk;
}

gf<cartesian_product<imfreq, brillouin_zone>, tensor_valued<4>>
chi0q_sum_nu(chi0q_t chi0q) {

  auto mesh = std::get<1>(chi0q.mesh());
  auto chi0q_w = make_gf<cartesian_product<imfreq, brillouin_zone>>(
      {std::get<0>(chi0q.mesh()), std::get<2>(chi0q.mesh())}, chi0q.target());

  double beta = mesh.domain().beta;

  chi0q_w(iw, k) << sum(chi0q(iw, inu, k), inu = mesh) / (beta * beta);

  return chi0q_w;
}

//  array<std::complex<double>, 4> chi0_n_sum_nu_tail_corr(gf<imfreq> chi0_n)

gf<cartesian_product<imfreq, brillouin_zone>, tensor_valued<4>>
chi0q_sum_nu_tail_corr_PH(chi0q_t chi0q) {

  auto mesh = std::get<1>(chi0q.mesh());
  auto chi0q_w = make_gf<cartesian_product<imfreq, brillouin_zone>>(
      {std::get<0>(chi0q.mesh()), std::get<2>(chi0q.mesh())}, chi0q.target());

  int nb = chi0q.target_shape()[0];
  double beta = mesh.domain().beta;

  auto wmesh = std::get<0>(chi0q.mesh());
  auto nmesh = std::get<1>(chi0q.mesh());
  auto qmesh = std::get<2>(chi0q.mesh());

  auto chi_target = chi0q.target();
  
  // for (auto const &w : wmesh) {
  //  for (auto const &q : qmesh) {

  auto arr = mpi_view(gf_mesh{wmesh, qmesh});

#pragma omp parallel for
  for (int idx = 0; idx < arr.size(); idx++) {
    auto &[w, q] = arr(idx);

    auto _ = all_t{};

    auto chi = make_gf<imfreq>(nmesh, chi_target);
    array<std::complex<double>, 4> dens(nb, nb, nb, nb);

    #pragma omp critical
    chi = chi0q[w, _, q];

    for (auto a : range(nb)) {
      for (auto b : range(nb)) {
        for (auto c : range(nb)) {
          for (auto d : range(nb)) {
            auto chi_abcd = slice_target_to_scalar(chi, a, b, c, d);
            //chi0q_w[w, q](a, b, c, d) = density(chi_abcd) / beta;
	    dens(a, b, c, d) = density(chi_abcd) / beta;
          }
        }
      }
    }

    #pragma omp critical
    chi0q_w[w, q] = dens;
    
  }

  chi0q_w = mpi_all_reduce(chi0q_w);
  return chi0q_w;
}

gf<imfreq, tensor_valued<4>> chi0q_sum_nu_q(chi0q_t chi0q) {

  auto mesh_b = std::get<0>(chi0q.mesh());
  auto mesh_f = std::get<1>(chi0q.mesh());
  auto mesh_k = std::get<2>(chi0q.mesh());

  auto chi0_w = make_gf<imfreq>(mesh_b, chi0q.target());

  for (auto const &[w, n, k] : chi0q.mesh())
    chi0_w[w] += chi0q[w, n, k];

  double nk = mesh_k.size();
  double beta = mesh_f.domain().beta;
  chi0_w = chi0_w / nk / (beta * beta);

  return chi0_w;
}

// ----------------------------------------------------
// chi

/*
chiq_t chiq_from_chi0q_and_gamma_PH(chi0q_vt chi0q, g2_iw_vt gamma_ph) {

  auto _ = all_t{};

  auto mb = std::get<0>(chi0q.mesh());
  auto mf = std::get<1>(chi0q.mesh());
  auto mbz = std::get<2>(chi0q.mesh());

  auto chiq = make_gf<chiq_t::mesh_t::var_t>({mbz, mb, mf, mf}, chi0q.target());

  for (auto const &k : mbz) {

    // -- Construct matrix version of chi0q_k

    // -- If we could make this a 1,1,1 g2_iw_t function and do the PH inverse
    // -- only in the target space we would save one global inverse!

    auto chi0q_k =
        make_gf<g2_iw_t::mesh_t::var_t>({mb, mf, mf}, chi0q.target());

    for (auto const &w : mb) {
      for (auto const &n : mf) {
        chi0q_k[w, n, n] = chi0q[w, n, k];
      }
    }

    g2_iw_t chiq_inv_k = inverse<Channel_t::PH>(chi0q_k) - gamma_ph;

    chiq[k, _, _, _] = inverse<Channel_t::PH>(chiq_inv_k);
  }

  return chiq;
}
*/

// ----------------------------------------------------
// chi

chiq_t chiq_from_chi0q_and_gamma_PH(chi0q_vt chi0q, g2_iw_vt gamma_ph) {

  auto _ = all_t{};

  auto mb = std::get<0>(chi0q.mesh());
  auto mf = std::get<1>(chi0q.mesh());
  auto mbz = std::get<2>(chi0q.mesh());

  auto chiq = make_gf<chiq_t::mesh_t::var_t>({mbz, mb, mf, mf}, chi0q.target());

  // for (auto const &k : mbz) {

#pragma omp parallel for
  for (int idx = 0; idx < mbz.size(); idx++) {
    auto iter = mbz.begin();
    iter += idx;
    auto k = *iter;

    auto chi0 = make_gf<g2_nn_t::mesh_t::var_t>({mf, mf}, chi0q.target());
    auto I = identity<Channel_t::PH>(chi0);

    for (auto const &w : mb) {

      chi0 *= 0.;
      for (auto const &n : mf) {
        chi0[n, n] = chi0q[w, n, k];
      }

      // this step could be optimized, using the diagonality of chi0 and I
      g2_nn_t denom = I - product<Channel_t::PH>(chi0, gamma_ph[w, _, _]);

      // also the last product here
      g2_nn_t chi = product<Channel_t::PH>(inverse<Channel_t::PH>(denom), chi0);

#pragma omp critical
      chiq[k, w, _, _] = chi;
    }
  }

  return chiq;
}

gf<cartesian_product<brillouin_zone, imfreq>, tensor_valued<4>>
chiq_sum_nu_from_chi0q_and_gamma_PH(chi0q_vt chi0q, g2_iw_vt gamma_ph) {

  auto _ = all_t{};

  auto mb = std::get<0>(chi0q.mesh());
  auto mf = std::get<1>(chi0q.mesh());
  auto mbz = std::get<2>(chi0q.mesh());

  double beta = mf.domain().beta;

  auto chi_kw = make_gf<cartesian_product<brillouin_zone, imfreq>>(
      {mbz, mb}, chi0q.target());

  // for (auto const &k : mbz) {

#pragma omp parallel for
  for (int idx = 0; idx < mbz.size(); idx++) {
    auto iter = mbz.begin();
    iter += idx;
    auto k = *iter;

    auto chi0 = make_gf<g2_nn_t::mesh_t::var_t>({mf, mf}, chi0q.target());
    auto I = identity<Channel_t::PH>(chi0);

    array<std::complex<double>, 4> tr_chi(chi0q.target_shape());

    for (auto const &w : mb) {

      chi0 *= 0.;
      for (auto const &n : mf) {
        chi0[n, n] = chi0q[w, n, k];
      }

      // this step could be optimized, using the diagonality of chi0 and I
      g2_nn_t denom = I - product<Channel_t::PH>(chi0, gamma_ph[w, _, _]);

      // also the last product here
      g2_nn_t chi = product<Channel_t::PH>(inverse<Channel_t::PH>(denom), chi0);

      // trace out fermionic frequencies
      tr_chi *= 0.0;
      for (auto const &n1 : mf)
        for (auto const &n2 : mf)
          tr_chi += chi[n1, n2];

      tr_chi /= beta * beta;

#pragma omp critical
      chi_kw[k, w] = tr_chi;
    }
  }

  return chi_kw;
}

gf<cartesian_product<brillouin_zone, imfreq>, tensor_valued<4>>
chiq_sum_nu_from_g_wk_and_gamma_PH(gk_iw_t g_wk, g2_iw_vt gamma_ph_wnn,
                                   int tail_corr_nwf) {

  auto _ = all_t{};

  auto target = gamma_ph_wnn.target();
  auto [fmesh_large, kmesh] = g_wk.mesh();
  auto [bmesh, fmesh, fmesh2] = gamma_ph_wnn.mesh();

  double beta = fmesh.domain().beta;

  auto chi_kw = make_gf<cartesian_product<brillouin_zone, imfreq>>(
      {kmesh, bmesh}, target);

  auto chi0_n = make_gf<imfreq>(fmesh, target);
  auto chi0_nn = make_gf<g2_nn_t::mesh_t::var_t>({fmesh, fmesh}, target);
  auto I = identity<Channel_t::PH>(chi0_nn);

  int nb = gamma_ph_wnn.target_shape()[0];

  gf_mesh<imfreq> fmesh_tail;
  if (tail_corr_nwf > 0)
    fmesh_tail = gf_mesh<imfreq>{beta, Fermion, tail_corr_nwf};
  else
    fmesh_tail = fmesh;

  if (fmesh_tail.size() < fmesh.size())
    TRIQS_RUNTIME_ERROR
        << "BSE: tail size has to be larger than gamma fermi mesh.\n";

  array<std::complex<double>, 4> tr_chi(gamma_ph_wnn.target_shape());
  array<std::complex<double>, 4> tr_chi0(gamma_ph_wnn.target_shape());
  array<std::complex<double>, 4> tr_chi0_tail_corr(gamma_ph_wnn.target_shape());

  for (auto const &[k, w] : mpi_view(gf_mesh{kmesh, bmesh})) {

    triqs::utility::timer t_chi0_n, t_chi0_tr, t_bse_1, t_bse_2, t_bse_3,
        t_chi_tr;

    // ----------------------------------------------------
    // Build the bare bubble at k, w

    t_chi0_n.start();
    std::cout << "BSE: chi0_n ";

    auto chi0_n_tail = chi0_n_from_g_wk_PH(w, k, fmesh_tail, g_wk);
    for (auto const &n : fmesh)
      chi0_n[n] = chi0_n_tail(n);

    std::cout << double(t_chi0_n) << " s\n";

    // ----------------------------------------------------
    // trace the bare bubble with and without tail corrections

    t_chi0_tr.start();
    std::cout << "BSE: Tr[chi0_n] ";

    // tr_chi0_tail_corr(a, b, c, d) << density(slice_target_to_scalar(chi0_n,
    // a, b, c, d)) / beta; // does not compile

    for (auto a : range(nb)) {
      for (auto b : range(nb)) {
        for (auto c : range(nb)) {
          for (auto d : range(nb)) {
            tr_chi0_tail_corr(a, b, c, d) =
                density(slice_target_to_scalar(chi0_n_tail, a, b, c, d)) / beta;
          }
        }
      }
    }

    tr_chi0(a, b, c, d) << sum(chi0_n(inu)(a, b, c, d), inu = fmesh) /
                               (beta * beta);

    std::cout << double(t_chi0_tr) << " s\n";

    // ----------------------------------------------------
    // Make two frequency object

    t_bse_1.start();
    std::cout << "BSE: chi0_nn ";

    for (auto const &n : fmesh)
      chi0_nn[n, n] = chi0_n[n];

    std::cout << double(t_bse_1) << " s\n";

    // ----------------------------------------------------

    t_bse_2.start();
    std::cout << "BSE: I - chi0 * gamma ";

    g2_nn_t denom = I - product<Channel_t::PH>(chi0_nn, gamma_ph_wnn[w, _, _]);

    std::cout << double(t_bse_2) << " s\n";

    t_bse_3.start();
    std::cout << "BSE: chi = [I - chi0 * gamma]^{-1} chi0 ";

    g2_nn_t chi_nn =
        product<Channel_t::PH>(inverse<Channel_t::PH>(denom), chi0_nn);

    std::cout << double(t_bse_3) << " s\n";

    // trace out fermionic frequencies
    std::cout << "BSE: Tr[chi] \n";
    tr_chi *= 0.0;
    for (auto const &[n1, n2] : chi_nn.mesh())
      tr_chi += chi_nn[n1, n2];
    tr_chi /= beta * beta;

    // 0th order high frequency correction using the bare bubble chi0
    tr_chi += tr_chi0_tail_corr - tr_chi0;

    chi_kw[k, w] = tr_chi;
  }

  chi_kw = mpi_all_reduce(chi_kw);

  return chi_kw;
}

gf<cartesian_product<brillouin_zone, imfreq>, tensor_valued<4>>
chiq_sum_nu_from_e_k_sigma_w_and_gamma_PH(double mu, ek_vt e_k, g_iw_vt sigma_w,
                                          g2_iw_vt gamma_ph_wnn,
                                          int tail_corr_nwf) {

  auto _ = all_t{};

  auto target = gamma_ph_wnn.target();
  // auto [fmesh_large, kmesh] = g_wk.mesh();

  auto kmesh = e_k.mesh();
  auto fmesh_large = sigma_w.mesh();

  auto [bmesh, fmesh, fmesh2] = gamma_ph_wnn.mesh();

  double beta = fmesh.domain().beta;

  auto chi_kw = make_gf<cartesian_product<brillouin_zone, imfreq>>(
      {kmesh, bmesh}, target);

  auto chi0_n = make_gf<imfreq>(fmesh, target);
  auto chi0_nn = make_gf<g2_nn_t::mesh_t::var_t>({fmesh, fmesh}, target);
  auto I = identity<Channel_t::PH>(chi0_nn);

  int nb = gamma_ph_wnn.target_shape()[0];

  gf_mesh<imfreq> fmesh_tail;
  if (tail_corr_nwf > 0)
    fmesh_tail = gf_mesh<imfreq>{beta, Fermion, tail_corr_nwf};
  else
    fmesh_tail = fmesh;

  if (fmesh_tail.size() < fmesh.size())
    TRIQS_RUNTIME_ERROR
        << "BSE: tail size has to be larger than gamma fermi mesh.\n";

  array<std::complex<double>, 4> tr_chi(gamma_ph_wnn.target_shape());
  array<std::complex<double>, 4> tr_chi0(gamma_ph_wnn.target_shape());
  array<std::complex<double>, 4> tr_chi0_tail_corr(gamma_ph_wnn.target_shape());

  for (auto const &[k, w] : mpi_view(gf_mesh{kmesh, bmesh})) {

    triqs::utility::timer t_chi0_n, t_chi0_tr, t_bse_1, t_bse_2, t_bse_3,
        t_chi_tr;

    // ----------------------------------------------------
    // Build the bare bubble at k, w

    t_chi0_n.start();
    std::cout << "BSE: chi0_n ";

    // auto chi0_n_tail = chi0_n_from_g_wk_PH(w, k, fmesh_tail, g_wk);

    auto chi0_n_tail =
        chi0_n_from_e_k_sigma_w_PH(w, k, fmesh_tail, mu, e_k, sigma_w);

    for (auto const &n : fmesh)
      chi0_n[n] = chi0_n_tail(n);

    std::cout << double(t_chi0_n) << " s\n";

    // ----------------------------------------------------
    // trace the bare bubble with and without tail corrections

    t_chi0_tr.start();
    std::cout << "BSE: Tr[chi0_n] ";

    // tr_chi0_tail_corr(a, b, c, d) << density(slice_target_to_scalar(chi0_n,
    // a, b, c, d)) / beta; // does not compile

    for (auto a : range(nb)) {
      for (auto b : range(nb)) {
        for (auto c : range(nb)) {
          for (auto d : range(nb)) {
            tr_chi0_tail_corr(a, b, c, d) =
                density(slice_target_to_scalar(chi0_n_tail, a, b, c, d)) / beta;
          }
        }
      }
    }

    tr_chi0(a, b, c, d) << sum(chi0_n(inu)(a, b, c, d), inu = fmesh) /
                               (beta * beta);

    std::cout << double(t_chi0_tr) << " s\n";

    // ----------------------------------------------------
    // Make two frequency object

    t_bse_1.start();
    std::cout << "BSE: chi0_nn ";

    for (auto const &n : fmesh)
      chi0_nn[n, n] = chi0_n[n];

    std::cout << double(t_bse_1) << " s\n";

    // ----------------------------------------------------

    t_bse_2.start();
    std::cout << "BSE: I - chi0 * gamma ";

    g2_nn_t denom = I - product<Channel_t::PH>(chi0_nn, gamma_ph_wnn[w, _, _]);

    std::cout << double(t_bse_2) << " s\n";

    t_bse_3.start();
    std::cout << "BSE: chi = [I - chi0 * gamma]^{-1} chi0 ";

    g2_nn_t chi_nn =
        product<Channel_t::PH>(inverse<Channel_t::PH>(denom), chi0_nn);

    std::cout << double(t_bse_3) << " s\n";

    // trace out fermionic frequencies
    std::cout << "BSE: Tr[chi] \n";
    tr_chi *= 0.0;
    for (auto const &[n1, n2] : chi_nn.mesh())
      tr_chi += chi_nn[n1, n2];
    tr_chi /= beta * beta;

    // 0th order high frequency correction using the bare bubble chi0
    tr_chi += tr_chi0_tail_corr - tr_chi0;

    chi_kw[k, w] = tr_chi;
  }

  chi_kw = mpi_all_reduce(chi_kw);

  return chi_kw;
}

gf<cartesian_product<brillouin_zone, imfreq>, tensor_valued<4>>
chiq_sum_nu(chiq_t chiq) {

  auto mesh_k = std::get<0>(chiq.mesh());
  auto mesh_b = std::get<1>(chiq.mesh());
  auto mesh_f = std::get<2>(chiq.mesh());
  auto chiq_w = make_gf<cartesian_product<brillouin_zone, imfreq>>(
      {mesh_k, mesh_b}, chiq.target());

  // Does not compile due to treatment of the tail (singularity)
  // chiq_w(k, iw) << sum(chiq(k, iw, inu, inup), inu=mesh, inup=mesh);

  for (auto const &[k, w, n1, n2] : chiq.mesh())
    chiq_w[k, w] += chiq[k, w, n1, n2];

  double beta = mesh_f.domain().beta;
  chiq_w = chiq_w / (beta * beta);

  return chiq_w;
}

gf<imfreq, tensor_valued<4>> chiq_sum_nu_q(chiq_t chiq) {

  auto mesh_k = std::get<0>(chiq.mesh());
  auto mesh_b = std::get<1>(chiq.mesh());
  auto mesh_f = std::get<2>(chiq.mesh());
  auto chi_w = make_gf<imfreq>(mesh_b, chiq.target());

  for (auto const &[k, w, n1, n2] : chiq.mesh())
    chi_w[w] += chiq[k, w, n1, n2];

  double nk = mesh_k.size();
  double beta = mesh_f.domain().beta;
  chi_w = chi_w / nk / (beta * beta);

  return chi_w;
}

} // namespace tprf
