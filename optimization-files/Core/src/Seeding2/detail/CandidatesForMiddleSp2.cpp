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

  if (container.size() < nMax) {
    container.emplace_back(spB, spM, spT, weight, zOrigin, isQuality);
    std::ranges::push_heap(container, comparator);
    return true;
  }

  if (weight <= container.front().weight) {
    return false;
  }

  std::ranges::pop_heap(container, comparator);
  container.back() = TripletCandidate2(spB, spM, spT, weight, zOrigin,
                                       isQuality);
  std::ranges::push_heap(container, comparator);

  return true;
}

void CandidatesForMiddleSp2::toSortedCandidates(
    std::vector<TripletCandidate2>& output) {
  output.clear();
  output.reserve(size());

  std::ranges::sort_heap(m_candidatesHigh, comparator);
  std::ranges::sort_heap(m_candidatesLow, comparator);

  output.insert(output.end(), m_candidatesHigh.begin(), m_candidatesHigh.end());
  output.insert(output.end(), m_candidatesLow.begin(), m_candidatesLow.end());

  clear();
}

}  // namespace Acts
