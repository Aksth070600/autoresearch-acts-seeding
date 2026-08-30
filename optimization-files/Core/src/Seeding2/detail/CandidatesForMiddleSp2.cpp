// This file is part of the ACTS project.
//
// Copyright (C) 2016 CERN for the benefit of the ACTS project
//
// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

#include "Acts/Seeding2/detail/CandidatesForMiddleSp2.hpp"

#include <algorithm>

namespace Acts {

CandidatesForMiddleSp2::CandidatesForMiddleSp2()
    : CandidatesForMiddleSp2(kNoSize, kNoSize) {}

CandidatesForMiddleSp2::CandidatesForMiddleSp2(Size nLow, Size nHigh)
    : m_maxSizeLow(nLow), m_maxSizeHigh(nHigh) {
  // Reserve enough memory for all collections
  m_storageLow.reserve(nLow != kNoSize ? nLow : 0);
  m_storageHigh.reserve(nHigh != kNoSize ? nHigh : 0);
}

void CandidatesForMiddleSp2::clear() {
  m_storageLow.clear();
  m_storageHigh.clear();
  m_indicesLow.clear();
  m_indicesHigh.clear();
}

bool CandidatesForMiddleSp2::push(SpacePointIndex2 spB, SpacePointIndex2 spM,
                                  SpacePointIndex2 spT, float weight,
                                  float zOrigin, bool isQuality) {
  // Decide in which collection this candidate may be added to according to the
  // isQuality boolean
  if (isQuality) {
    return push(m_indicesHigh, m_storageHigh, m_maxSizeHigh, spB, spM, spT,
                weight, zOrigin, isQuality);
  }
  return push(m_indicesLow, m_storageLow, m_maxSizeLow, spB, spM, spT, weight,
              zOrigin, isQuality);
}

bool CandidatesForMiddleSp2::push(Container& container, Storage& storage,
                                  Size nMax, SpacePointIndex2 spB,
                                  SpacePointIndex2 spM, SpacePointIndex2 spT,
                                  float weight, float zOrigin, bool isQuality) {
  if (nMax == 0) {
    return false;
  }

  if (container.size() < nMax) {
    // If there is still space, add anything
    storage.emplace_back(spB, spM, spT, weight, zOrigin, isQuality);
    container.emplace_back(weight, storage.size() - 1);
    std::ranges::push_heap(container, comparator);
    return true;
  }

  // If no space, replace one if quality is enough
  // Compare to element with lowest weight
  const auto [smallestWeight, smallestIndex] = container.front();
  if (weight <= smallestWeight) {
    return false;
  }

  // Remove element with lower weight and add this one
  storage[smallestIndex] =
      TripletCandidate2(spB, spM, spT, weight, zOrigin, isQuality);
  std::ranges::pop_heap(container, comparator);
  container.back() = {weight, smallestIndex};
  std::ranges::push_heap(container, comparator);

  return true;
}

void CandidatesForMiddleSp2::toSortedCandidates(
    std::vector<TripletCandidate2>& output) {
  output.clear();
  output.reserve(size());

  std::ranges::sort_heap(m_indicesHigh, comparator);
  std::ranges::sort_heap(m_indicesLow, comparator);

  for (const auto& [weight, index] : m_indicesHigh) {
    output.emplace_back(m_storageHigh[index]);
  }
  for (const auto& [weight, index] : m_indicesLow) {
    output.emplace_back(m_storageLow[index]);
  }

  clear();
}

}  // namespace Acts
