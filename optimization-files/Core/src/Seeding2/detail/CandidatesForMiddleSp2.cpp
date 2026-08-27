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

  if (container.size() < nMax) {
    m_storage.emplace_back(spB, spM, spT, weight, zOrigin, isQuality);
    container.emplace(weight, m_storage.size() - 1);
    return true;
  }

  const auto smallest = container.begin();
  if (weight <= smallest->first) {
    return false;
  }

  const Index smallestIndex = smallest->second;
  m_storage[smallestIndex] =
      TripletCandidate2(spB, spM, spT, weight, zOrigin, isQuality);
  container.erase(smallest);
  container.emplace(weight, smallestIndex);
  return true;
}

void CandidatesForMiddleSp2::toSortedCandidates(
    std::vector<TripletCandidate2>& output) {
  output.clear();
  output.reserve(size());

  for (auto item = m_indicesHigh.rbegin(); item != m_indicesHigh.rend();
       ++item) {
    output.emplace_back(m_storage[item->second]);
  }
  for (auto item = m_indicesLow.rbegin(); item != m_indicesLow.rend(); ++item) {
    output.emplace_back(m_storage[item->second]);
  }

  clear();
}

}  // namespace Acts
