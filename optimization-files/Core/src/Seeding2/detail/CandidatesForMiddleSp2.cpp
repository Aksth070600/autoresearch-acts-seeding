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
  m_candidatesLow.reserve(nLow != kNoSize ? nLow : 0);
  m_candidatesHigh.reserve(nHigh != kNoSize ? nHigh : 0);
}

void CandidatesForMiddleSp2::clear() {
  m_candidatesLow.clear();
  m_candidatesHigh.clear();
}

bool CandidatesForMiddleSp2::push(SpacePointIndex2 spB, SpacePointIndex2 spM,
                                  SpacePointIndex2 spT, float weight,
                                  float zOrigin, bool isQuality) {
  // Decide in which collection this candidate may be added to according to the
  // isQuality boolean
  if (isQuality) {
    return push(m_candidatesHigh, m_maxSizeHigh, spB, spM, spT, weight,
                zOrigin, isQuality);
  }
  return push(m_candidatesLow, m_maxSizeLow, spB, spM, spT, weight, zOrigin,
              isQuality);
}

bool CandidatesForMiddleSp2::push(Container& container, Size nMax,
                                  SpacePointIndex2 spB, SpacePointIndex2 spM,
                                  SpacePointIndex2 spT, float weight,
                                  float zOrigin, bool isQuality) {
  if (nMax == 0) {
    return false;
  }

  container.emplace_back(spB, spM, spT, weight, zOrigin, isQuality);
  return true;
}

void CandidatesForMiddleSp2::toSortedCandidates(
    std::vector<TripletCandidate2>& output) {
  output.clear();
  output.reserve(size());

  const auto appendBest = [&](Container& candidates, Size maximum) {
    const Size retained = retainedSize(candidates, maximum);
    std::ranges::partial_sort(candidates, candidates.begin() + retained,
                              comparator);
    output.insert(output.end(), candidates.begin(),
                  candidates.begin() + retained);
  };
  appendBest(m_candidatesHigh, m_maxSizeHigh);
  appendBest(m_candidatesLow, m_maxSizeLow);

  clear();
}

}  // namespace Acts
