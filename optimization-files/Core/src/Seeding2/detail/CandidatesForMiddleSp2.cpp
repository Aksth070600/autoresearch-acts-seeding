// This file is part of the ACTS project.
//
// Copyright (C) 2016 CERN for the benefit of the ACTS project
//
// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

#include "Acts/Seeding2/detail/CandidatesForMiddleSp2.hpp"

#include <algorithm>
#include <cassert>

namespace Acts {

CandidatesForMiddleSp2::CandidatesForMiddleSp2()
    : CandidatesForMiddleSp2(kNoSize, kNoSize) {}

CandidatesForMiddleSp2::CandidatesForMiddleSp2(Size nLow, Size nHigh)
    : m_maxSizeLow(nLow), m_maxSizeHigh(nHigh) {
  m_fixedStorage = nLow != kNoSize && nHigh != kNoSize;
  if (m_fixedStorage) {
    m_storage.resize(nLow + nHigh);
  }
}

void CandidatesForMiddleSp2::clear() {
  m_middleSp.reset();
  if (!m_fixedStorage) {
    m_storage.clear();
  }
  m_nextSlot = 0;
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

  if (m_middleSp.has_value()) {
    assert(*m_middleSp == spM &&
           "CandidatesForMiddleSp2 received more than one middle space point");
  } else {
    m_middleSp = spM;
  }

  if (container.size() < nMax) {
    Index slot = 0;
    if (m_fixedStorage) {
      slot = m_nextSlot++;
      m_storage[slot] = {spB, spT, weight, zOrigin, isQuality};
    } else {
      m_storage.push_back({spB, spT, weight, zOrigin, isQuality});
      slot = static_cast<Index>(m_storage.size() - 1);
    }
    container.emplace_back(weight, slot);
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
  m_storage[smallestIndex] = {spB, spT, weight, zOrigin, isQuality};
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

  assert((size() == 0 || m_middleSp.has_value()) &&
         "retained candidates require a middle space point");
  const auto appendCandidate = [&](Index index) {
    const StoredCandidate& candidate = m_storage[index];
    output.emplace_back(candidate.bottom, *m_middleSp, candidate.top,
                        candidate.weight, candidate.zOrigin,
                        candidate.isQuality);
  };
  for (const auto& [weight, index] : m_indicesHigh) {
    appendCandidate(index);
  }
  for (const auto& [weight, index] : m_indicesLow) {
    appendCandidate(index);
  }

  clear();
}

}  // namespace Acts
