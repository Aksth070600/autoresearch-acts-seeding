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
  m_storage.reserve((nLow != kNoSize ? nLow : 0) +
                    (nHigh != kNoSize ? nHigh : 0));
}

void CandidatesForMiddleSp2::clear() {
  m_storage.clear();
  m_indicesLow.clear();
  m_indicesHigh.clear();
}

bool CandidatesForMiddleSp2::push(SpacePointIndex2 spB, SpacePointIndex2 spM,
                                  SpacePointIndex2 spT, float weight,
                                  float zOrigin, bool isQuality) {
  // Decide in which collection this candidate may be added to according to the
  // isQuality boolean
  if (isQuality) {
    return push(m_indicesHigh, m_maxSizeHigh, spB, spM, spT, weight, zOrigin,
                isQuality);
  }
  return push(m_indicesLow, m_maxSizeLow, spB, spM, spT, weight, zOrigin,
              isQuality);
}

bool CandidatesForMiddleSp2::push(Container& container, Size nMax,
                                  SpacePointIndex2 spB, SpacePointIndex2 spM,
                                  SpacePointIndex2 spT, float weight,
                                  float zOrigin, bool isQuality) {
  if (nMax == 0) {
    return false;
  }

  const auto insertionPosition = [&](float candidateWeight) {
    return std::ranges::lower_bound(
        container, candidateWeight,
        [](float left, float right) { return left > right; },
        [](const WeightIndex& item) { return item.first; });
  };

  if (container.size() < nMax) {
    m_storage.emplace_back(spB, spM, spT, weight, zOrigin, isQuality);
    container.insert(insertionPosition(weight),
                     {weight, m_storage.size() - 1});
    return true;
  }

  // The list is descending, so its last entry is the rejection threshold.
  const auto [smallestWeight, smallestIndex] = container.back();
  if (weight <= smallestWeight) {
    return false;
  }

  m_storage[smallestIndex] =
      TripletCandidate2(spB, spM, spT, weight, zOrigin, isQuality);
  container.pop_back();
  container.insert(insertionPosition(weight), {weight, smallestIndex});

  return true;
}

void CandidatesForMiddleSp2::toSortedCandidates(
    std::vector<TripletCandidate2>& output) {
  output.clear();
  output.reserve(size());

  for (const auto& [weight, index] : m_indicesHigh) {
    output.emplace_back(m_storage[index]);
  }
  for (const auto& [weight, index] : m_indicesLow) {
    output.emplace_back(m_storage[index]);
  }

  clear();
}

}  // namespace Acts
