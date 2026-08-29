// This file is part of the autoresearch ACTS seeding project.

#include "ActsExamples/Io/Root/OwnedSeedingDataset.hpp"

#include "Acts/Definitions/PdgParticle.hpp"
#include "Acts/EventData/SourceLink.hpp"
#include "Acts/EventData/SpacePointColumns.hpp"
#include "Acts/Geometry/GeometryIdentifier.hpp"
#include "ActsExamples/EventData/IndexSourceLink.hpp"
#include "ActsExamples/Framework/AlgorithmContext.hpp"
#include "ActsFatras/EventData/GenerationProcess.hpp"
#include "ActsFatras/EventData/SimulationOutcome.hpp"

#include "Sha256.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <ios>
#include <limits>
#include <numeric>
#include <set>
#include <span>
#include <stdexcept>
#include <string_view>
#include <tuple>
#include <type_traits>
#include <utility>

#include <Compression.h>
#include <TBranch.h>
#include <TFile.h>
#include <TKey.h>
#include <TObjArray.h>
#include <TObject.h>
#include <TTree.h>
#include <TUUID.h>

namespace ActsExamples {

// This is the only code allowed to bypass Particle::setDirection's
// normalization. Particle.hpp grants friendship only to this project-owned
// type. The reader calls it after validating and hashing the complete event.
struct OwnedSeedingParticleDirectionRestorer {
  static void restoreValidated(ActsFatras::Particle& particle,
                               const Acts::Vector3& direction) {
    particle.m_direction = direction;
  }
};

namespace {

using ULong = unsigned long long;
using OwnedSeedingDetail::Sha256;
using OwnedSeedingDetail::hexDigest;

constexpr std::string_view kCanonicalStream =
    "acts-owned-seeding-canonical-v1";
constexpr std::array<std::string_view, 6> kSections = {
    "measurements",          "space_points",       "particles",
    "selected_particles",    "measurement_particles",
    "particle_measurements"};

#define OWNED_VECTOR_FIELDS(X)                                                \
  X(measurementIndex, ULong, "measurement_index")                           \
  X(measurementGeometryId, ULong, "measurement_geometry_id")                \
  X(measurementSize, unsigned char, "measurement_size")                     \
  X(measurementValueOffset, ULong, "measurement_value_offset")              \
  X(measurementSubspaceIndex, unsigned char,                                 \
    "measurement_subspace_index")                                           \
  X(measurementParameter, double, "measurement_parameter")                  \
  X(measurementCovarianceOffset, ULong,                                      \
    "measurement_covariance_offset")                                        \
  X(measurementCovariance, double, "measurement_covariance")                \
  X(spacePointIndex, unsigned int, "spacepoint_index")                       \
  X(spacePointKind, unsigned char, "spacepoint_kind")                        \
  X(spacePointOverlapClass, unsigned char, "spacepoint_overlap_class")       \
  X(spacePointX, float, "spacepoint_x")                                      \
  X(spacePointY, float, "spacepoint_y")                                      \
  X(spacePointZ, float, "spacepoint_z")                                      \
  X(spacePointR, float, "spacepoint_r")                                      \
  X(spacePointTimeValid, unsigned char, "spacepoint_time_valid")             \
  X(spacePointTime, float, "spacepoint_time")                                \
  X(spacePointVarianceR, float, "spacepoint_variance_r")                     \
  X(spacePointVarianceZ, float, "spacepoint_variance_z")                     \
  X(spacePointSourceOffset, ULong, "spacepoint_source_offset")               \
  X(spacePointSourceGeometryId, ULong,                                       \
    "spacepoint_source_geometry_id")                                         \
  X(spacePointSourceMeasurementIndex, ULong,                                 \
    "spacepoint_source_measurement_index")                                   \
  X(particleBarcode, unsigned int, "particle_barcode")                       \
  X(particleBarcodeHash, ULong, "particle_barcode_hash")                     \
  X(particlePdg, int, "particle_pdg")                                        \
  X(particleProcess, unsigned int, "particle_process")                       \
  X(particleCharge, double, "particle_charge")                               \
  X(particleMass, double, "particle_mass")                                   \
  X(particleInitialPosition4, double, "particle_initial_position4")          \
  X(particleInitialDirection3, double, "particle_initial_direction3")        \
  X(particleInitialMomentum, double, "particle_initial_momentum")            \
  X(particleInitialProperTime, double, "particle_initial_proper_time")       \
  X(particleInitialPathInX0, double, "particle_initial_path_in_x0")          \
  X(particleInitialPathInL0, double, "particle_initial_path_in_l0")          \
  X(particleInitialNumberOfHits, unsigned int,                               \
    "particle_initial_number_of_hits")                                       \
  X(particleInitialOutcome, unsigned int, "particle_initial_outcome")        \
  X(particleFinalPosition4, double, "particle_final_position4")              \
  X(particleFinalDirection3, double, "particle_final_direction3")            \
  X(particleFinalMomentum, double, "particle_final_momentum")                \
  X(particleFinalProperTime, double, "particle_final_proper_time")           \
  X(particleFinalPathInX0, double, "particle_final_path_in_x0")              \
  X(particleFinalPathInL0, double, "particle_final_path_in_l0")              \
  X(particleFinalNumberOfHits, unsigned int,                                 \
    "particle_final_number_of_hits")                                         \
  X(particleFinalOutcome, unsigned int, "particle_final_outcome")            \
  X(particleSelected, unsigned char, "particle_selected")                    \
  X(measurementParticlesOrdinal, ULong,                                      \
    "measurement_particles_ordinal")                                        \
  X(measurementParticlesMeasurementIndex, ULong,                             \
    "measurement_particles_measurement_index")                              \
  X(measurementParticlesBarcode, unsigned int,                               \
    "measurement_particles_barcode")                                        \
  X(particleMeasurementsOrdinal, ULong,                                      \
    "particle_measurements_ordinal")                                        \
  X(particleMeasurementsBarcode, unsigned int,                               \
    "particle_measurements_barcode")                                        \
  X(particleMeasurementsMeasurementIndex, ULong,                             \
    "particle_measurements_measurement_index")

#define OWNED_STRING_FIELDS(X)                                                \
  X(measurementsSha256, "measurements_sha256")                              \
  X(spacePointsSha256, "spacepoints_sha256")                                \
  X(particlesSha256, "particles_sha256")                                    \
  X(selectedParticlesSha256, "selected_particles_sha256")                   \
  X(measurementParticlesSha256, "measurement_particles_sha256")             \
  X(particleMeasurementsSha256, "particle_measurements_sha256")             \
  X(eventSemanticSha256, "event_semantic_sha256")

struct Payload {
  unsigned int eventOrdinal = 0;
  ULong eventId = 0;
  ULong measurementCount = 0;
  ULong spacePointCount = 0;
  ULong particleCount = 0;
  ULong selectedParticleCount = 0;
  ULong measurementParticlesCount = 0;
  ULong particleMeasurementsCount = 0;
#define DECLARE_VECTOR(member, type, branch) std::vector<type> member;
  OWNED_VECTOR_FIELDS(DECLARE_VECTOR)
#undef DECLARE_VECTOR
#define DECLARE_STRING(member, branch) std::string member;
  OWNED_STRING_FIELDS(DECLARE_STRING)
#undef DECLARE_STRING

  void clear() {
    eventOrdinal = 0;
    eventId = 0;
    measurementCount = 0;
    spacePointCount = 0;
    particleCount = 0;
    selectedParticleCount = 0;
    measurementParticlesCount = 0;
    particleMeasurementsCount = 0;
#define CLEAR_VECTOR(member, type, branch) member.clear();
    OWNED_VECTOR_FIELDS(CLEAR_VECTOR)
#undef CLEAR_VECTOR
#define CLEAR_STRING(member, branch) member.clear();
    OWNED_STRING_FIELDS(CLEAR_STRING)
#undef CLEAR_STRING
  }
};

struct ReadPointers {
#define DECLARE_POINTER(member, type, branch) std::vector<type>* member = nullptr;
  OWNED_VECTOR_FIELDS(DECLARE_POINTER)
#undef DECLARE_POINTER
#define DECLARE_STRING_POINTER(member, branch) std::string* member = nullptr;
  OWNED_STRING_FIELDS(DECLARE_STRING_POINTER)
#undef DECLARE_STRING_POINTER

  void pointTo(Payload& payload) {
#define POINT_VECTOR(member, type, branch) member = &payload.member;
    OWNED_VECTOR_FIELDS(POINT_VECTOR)
#undef POINT_VECTOR
#define POINT_STRING(member, branch) member = &payload.member;
    OWNED_STRING_FIELDS(POINT_STRING)
#undef POINT_STRING
  }
};

void require(bool condition, std::string_view message) {
  if (!condition) {
    throw std::runtime_error(std::string("owned seeding dataset: ") +
                             std::string(message));
  }
}

template <typename T>
void requireSize(const std::vector<T>& values, std::size_t size,
                 std::string_view name) {
  if (values.size() != size) {
    throw std::runtime_error("owned seeding dataset: " + std::string(name) +
                             " size mismatch");
  }
}

template <typename T>
void requireFinite(T value, std::string_view name) {
  if (!std::isfinite(value)) {
    throw std::runtime_error("owned seeding dataset: non-finite " +
                             std::string(name));
  }
}

class Encoder {
 public:
  void u8(std::uint8_t value) { bytes(value); }
  void u32(std::uint32_t value) { little(value); }
  void i32(std::int32_t value) {
    little(std::bit_cast<std::uint32_t>(value));
  }
  void u64(std::uint64_t value) { little(value); }
  void f32(float value) { little(std::bit_cast<std::uint32_t>(value)); }
  void f64(double value) { little(std::bit_cast<std::uint64_t>(value)); }

  void text(std::string_view value) {
    u64(value.size());
    m_hash.update(std::as_bytes(std::span(value.data(), value.size())));
  }

  void digestBytes(const std::array<std::uint8_t, 32>& digest) {
    u64(digest.size());
    m_hash.update(std::as_bytes(std::span(digest)));
  }

  std::array<std::uint8_t, 32> digest() { return m_hash.finalize(); }

 private:
  void bytes(std::uint8_t value) {
    m_hash.update(std::as_bytes(std::span(&value, 1)));
  }

  template <std::unsigned_integral T>
  void little(T value) {
    std::array<std::uint8_t, sizeof(T)> data{};
    for (std::size_t i = 0; i < data.size(); ++i) {
      data[i] = static_cast<std::uint8_t>((value >> (8 * i)) & 0xffu);
    }
    m_hash.update(std::as_bytes(std::span(data)));
  }

  Sha256 m_hash;
};

SimBarcode barcodeAt(const std::vector<unsigned int>& flat, std::size_t index) {
  const std::size_t offset = 5 * index;
  require(offset + 5 <= flat.size(), "truncated barcode array");
  require(flat[offset] <=
              std::numeric_limits<SimBarcode::PrimaryVertexId>::max() &&
              flat[offset + 1] <=
                  std::numeric_limits<SimBarcode::SecondaryVertexId>::max() &&
              flat[offset + 3] <=
                  std::numeric_limits<SimBarcode::GenerationId>::max(),
          "barcode component exceeds its integer range");
  return SimBarcode()
      .withVertexPrimary(
          static_cast<SimBarcode::PrimaryVertexId>(flat[offset]))
      .withVertexSecondary(
          static_cast<SimBarcode::SecondaryVertexId>(flat[offset + 1]))
      .withParticle(static_cast<SimBarcode::ParticleId>(flat[offset + 2]))
      .withGeneration(
          static_cast<SimBarcode::GenerationId>(flat[offset + 3]))
      .withSubParticle(
          static_cast<SimBarcode::SubParticleId>(flat[offset + 4]));
}

void appendBarcode(std::vector<unsigned int>& output, SimBarcode barcode) {
  output.push_back(barcode.vertexPrimary());
  output.push_back(barcode.vertexSecondary());
  output.push_back(barcode.particle());
  output.push_back(barcode.generation());
  output.push_back(barcode.subParticle());
}

void encodeBarcode(Encoder& encoder, SimBarcode barcode) {
  encoder.u32(barcode.vertexPrimary());
  encoder.u32(barcode.vertexSecondary());
  encoder.u32(barcode.particle());
  encoder.u32(barcode.generation());
  encoder.u32(barcode.subParticle());
}

void appendState(Payload& payload, const SimParticleState& state,
                 bool initial) {
  auto& position = initial ? payload.particleInitialPosition4
                           : payload.particleFinalPosition4;
  auto& direction = initial ? payload.particleInitialDirection3
                            : payload.particleFinalDirection3;
  auto& momentum = initial ? payload.particleInitialMomentum
                           : payload.particleFinalMomentum;
  auto& properTime = initial ? payload.particleInitialProperTime
                             : payload.particleFinalProperTime;
  auto& pathInX0 = initial ? payload.particleInitialPathInX0
                           : payload.particleFinalPathInX0;
  auto& pathInL0 = initial ? payload.particleInitialPathInL0
                           : payload.particleFinalPathInL0;
  auto& hits = initial ? payload.particleInitialNumberOfHits
                       : payload.particleFinalNumberOfHits;
  auto& outcome = initial ? payload.particleInitialOutcome
                          : payload.particleFinalOutcome;

  for (double value : state.fourPosition()) {
    requireFinite(value, "particle position");
    position.push_back(value);
  }
  for (double value : state.direction()) {
    requireFinite(value, "particle direction");
    direction.push_back(value);
  }
  requireFinite(state.absoluteMomentum(), "particle momentum");
  requireFinite(state.properTime(), "particle proper time");
  requireFinite(state.pathInX0(), "particle path in X0");
  requireFinite(state.pathInL0(), "particle path in L0");
  require(state.absoluteMomentum() >= 0, "negative particle momentum");
  require(state.pathInX0() >= 0 && state.pathInL0() >= 0,
          "negative particle material path");
  momentum.push_back(state.absoluteMomentum());
  properTime.push_back(state.properTime());
  pathInX0.push_back(state.pathInX0());
  pathInL0.push_back(state.pathInL0());
  hits.push_back(state.numberOfHits());
  outcome.push_back(static_cast<unsigned int>(state.outcome()));
}

void encodeState(Encoder& encoder, const Payload& payload, std::size_t index,
                 bool initial) {
  const auto& position = initial ? payload.particleInitialPosition4
                                 : payload.particleFinalPosition4;
  const auto& direction = initial ? payload.particleInitialDirection3
                                  : payload.particleFinalDirection3;
  const auto& momentum = initial ? payload.particleInitialMomentum
                                 : payload.particleFinalMomentum;
  const auto& properTime = initial ? payload.particleInitialProperTime
                                   : payload.particleFinalProperTime;
  const auto& pathInX0 = initial ? payload.particleInitialPathInX0
                                 : payload.particleFinalPathInX0;
  const auto& pathInL0 = initial ? payload.particleInitialPathInL0
                                 : payload.particleFinalPathInL0;
  const auto& hits = initial ? payload.particleInitialNumberOfHits
                             : payload.particleFinalNumberOfHits;
  const auto& outcome = initial ? payload.particleInitialOutcome
                                : payload.particleFinalOutcome;
  for (std::size_t component = 0; component < 4; ++component) {
    encoder.f64(position[4 * index + component]);
  }
  for (std::size_t component = 0; component < 3; ++component) {
    encoder.f64(direction[3 * index + component]);
  }
  encoder.f64(momentum[index]);
  encoder.f64(properTime[index]);
  encoder.f64(pathInX0[index]);
  encoder.f64(pathInL0[index]);
  encoder.u32(hits[index]);
  encoder.u32(outcome[index]);
}

std::array<std::uint8_t, 32> hashMeasurements(const Payload& payload) {
  Encoder encoder;
  encoder.text(kCanonicalStream);
  encoder.text("measurements");
  encoder.u64(payload.measurementCount);
  for (std::size_t index = 0; index < payload.measurementCount; ++index) {
    const std::size_t valueBegin = payload.measurementValueOffset[index];
    const std::size_t valueEnd = payload.measurementValueOffset[index + 1];
    const std::size_t covarianceBegin =
        payload.measurementCovarianceOffset[index];
    const std::size_t covarianceEnd =
        payload.measurementCovarianceOffset[index + 1];
    const std::size_t size = payload.measurementSize[index];
    encoder.u64(payload.measurementIndex[index]);
    encoder.u64(payload.measurementGeometryId[index]);
    encoder.u8(payload.measurementSize[index]);
    encoder.u64(size);
    for (std::size_t offset = valueBegin; offset < valueEnd; ++offset) {
      encoder.u8(payload.measurementSubspaceIndex[offset]);
    }
    encoder.u64(size);
    for (std::size_t offset = valueBegin; offset < valueEnd; ++offset) {
      encoder.f64(payload.measurementParameter[offset]);
    }
    encoder.u64(size * size);
    for (std::size_t offset = covarianceBegin; offset < covarianceEnd;
         ++offset) {
      encoder.f64(payload.measurementCovariance[offset]);
    }
  }
  return encoder.digest();
}

std::array<std::uint8_t, 32> hashSpacePoints(const Payload& payload) {
  Encoder encoder;
  encoder.text(kCanonicalStream);
  encoder.text("space_points");
  encoder.u64(payload.spacePointCount);
  for (std::size_t index = 0; index < payload.spacePointCount; ++index) {
    encoder.u32(payload.spacePointIndex[index]);
    encoder.u8(payload.spacePointKind[index]);
    encoder.u8(payload.spacePointOverlapClass[index]);
    encoder.f32(payload.spacePointX[index]);
    encoder.f32(payload.spacePointY[index]);
    encoder.f32(payload.spacePointZ[index]);
    encoder.f32(payload.spacePointR[index]);
    encoder.u8(payload.spacePointTimeValid[index]);
    encoder.f32(payload.spacePointTime[index]);
    encoder.f32(payload.spacePointVarianceR[index]);
    encoder.f32(payload.spacePointVarianceZ[index]);
    const std::size_t begin = payload.spacePointSourceOffset[index];
    const std::size_t end = payload.spacePointSourceOffset[index + 1];
    encoder.u64(end - begin);
    for (std::size_t offset = begin; offset < end; ++offset) {
      encoder.u64(payload.spacePointSourceGeometryId[offset]);
      encoder.u64(payload.spacePointSourceMeasurementIndex[offset]);
    }
  }
  return encoder.digest();
}

std::array<std::uint8_t, 32> hashParticles(const Payload& payload) {
  Encoder encoder;
  encoder.text(kCanonicalStream);
  encoder.text("particles");
  encoder.u64(payload.particleCount);
  for (std::size_t index = 0; index < payload.particleCount; ++index) {
    encodeBarcode(encoder, barcodeAt(payload.particleBarcode, index));
    encoder.i32(payload.particlePdg[index]);
    encoder.u32(payload.particleProcess[index]);
    encoder.f64(payload.particleCharge[index]);
    encoder.f64(payload.particleMass[index]);
    encodeState(encoder, payload, index, true);
    encodeState(encoder, payload, index, false);
    encoder.u8(payload.particleSelected[index]);
  }
  return encoder.digest();
}

std::array<std::uint8_t, 32> hashSelectedParticles(const Payload& payload) {
  Encoder encoder;
  encoder.text(kCanonicalStream);
  encoder.text("selected_particles");
  encoder.u64(payload.selectedParticleCount);
  for (std::size_t index = 0; index < payload.particleCount; ++index) {
    if (payload.particleSelected[index] != 0) {
      encodeBarcode(encoder, barcodeAt(payload.particleBarcode, index));
    }
  }
  return encoder.digest();
}

std::array<std::uint8_t, 32> hashMeasurementParticles(
    const Payload& payload) {
  Encoder encoder;
  encoder.text(kCanonicalStream);
  encoder.text("measurement_particles");
  encoder.u64(payload.measurementParticlesCount);
  for (std::size_t index = 0; index < payload.measurementParticlesCount;
       ++index) {
    encoder.u64(payload.measurementParticlesOrdinal[index]);
    encoder.u64(payload.measurementParticlesMeasurementIndex[index]);
    encodeBarcode(encoder,
                  barcodeAt(payload.measurementParticlesBarcode, index));
  }
  return encoder.digest();
}

std::array<std::uint8_t, 32> hashParticleMeasurements(
    const Payload& payload) {
  Encoder encoder;
  encoder.text(kCanonicalStream);
  encoder.text("particle_measurements");
  encoder.u64(payload.particleMeasurementsCount);
  for (std::size_t index = 0; index < payload.particleMeasurementsCount;
       ++index) {
    encoder.u64(payload.particleMeasurementsOrdinal[index]);
    encodeBarcode(encoder,
                  barcodeAt(payload.particleMeasurementsBarcode, index));
    encoder.u64(payload.particleMeasurementsMeasurementIndex[index]);
  }
  return encoder.digest();
}

OwnedSeedingEventSummary validateAndHash(
    Payload& payload, const Acts::TrackingGeometry* trackingGeometry) {
  const std::size_t nMeasurements = payload.measurementCount;
  requireSize(payload.measurementIndex, nMeasurements, "measurement_index");
  requireSize(payload.measurementGeometryId, nMeasurements,
              "measurement_geometry_id");
  requireSize(payload.measurementSize, nMeasurements, "measurement_size");
  requireSize(payload.measurementValueOffset, nMeasurements + 1,
              "measurement_value_offset");
  requireSize(payload.measurementCovarianceOffset, nMeasurements + 1,
              "measurement_covariance_offset");
  require(payload.measurementValueOffset.front() == 0 &&
              payload.measurementCovarianceOffset.front() == 0,
          "measurement CSR offsets must start at zero");
  require(payload.measurementValueOffset.back() ==
              payload.measurementParameter.size() &&
              payload.measurementSubspaceIndex.size() ==
                  payload.measurementParameter.size(),
          "measurement value CSR endpoint mismatch");
  require(payload.measurementCovarianceOffset.back() ==
              payload.measurementCovariance.size(),
          "measurement covariance CSR endpoint mismatch");
  for (std::size_t index = 0; index < nMeasurements; ++index) {
    require(payload.measurementIndex[index] == index,
            "measurement indices must be ordered and contiguous");
    const std::uint64_t geometryValue = payload.measurementGeometryId[index];
    require(geometryValue != 0, "zero measurement geometry ID");
    if (trackingGeometry != nullptr) {
      require(trackingGeometry->findSurface(
                  Acts::GeometryIdentifier(geometryValue)) != nullptr,
              "unresolved measurement geometry ID");
    }
    const std::size_t size = payload.measurementSize[index];
    require(size >= 1 && size <= Acts::eBoundSize,
            "measurement size outside 1..6");
    const std::size_t valueBegin = payload.measurementValueOffset[index];
    const std::size_t valueEnd = payload.measurementValueOffset[index + 1];
    const std::size_t covarianceBegin =
        payload.measurementCovarianceOffset[index];
    const std::size_t covarianceEnd =
        payload.measurementCovarianceOffset[index + 1];
    require(valueEnd >= valueBegin && valueEnd - valueBegin == size,
            "malformed measurement value CSR offsets");
    require(covarianceEnd >= covarianceBegin &&
                covarianceEnd - covarianceBegin == size * size,
            "malformed measurement covariance CSR offsets");
    unsigned int previous = 0;
    for (std::size_t offset = valueBegin; offset < valueEnd; ++offset) {
      const unsigned int subspace =
          payload.measurementSubspaceIndex[offset];
      require(subspace < Acts::eBoundSize,
              "measurement subspace index out of range");
      require(offset == valueBegin || previous < subspace,
              "measurement subspace indices not ordered and unique");
      previous = subspace;
      requireFinite(payload.measurementParameter[offset],
                    "measurement parameter");
    }
    for (std::size_t offset = covarianceBegin; offset < covarianceEnd;
         ++offset) {
      requireFinite(payload.measurementCovariance[offset],
                    "measurement covariance");
    }
  }

  const std::size_t nSpacePoints = payload.spacePointCount;
#define REQUIRE_SP_SIZE(member, type, branch)                                 \
  if constexpr (std::string_view(branch).starts_with("spacepoint_") &&       \
                !std::string_view(branch).starts_with(                        \
                    "spacepoint_source_")) {                                 \
  }
  requireSize(payload.spacePointIndex, nSpacePoints, "spacepoint_index");
  requireSize(payload.spacePointKind, nSpacePoints, "spacepoint_kind");
  requireSize(payload.spacePointOverlapClass, nSpacePoints,
              "spacepoint_overlap_class");
  requireSize(payload.spacePointX, nSpacePoints, "spacepoint_x");
  requireSize(payload.spacePointY, nSpacePoints, "spacepoint_y");
  requireSize(payload.spacePointZ, nSpacePoints, "spacepoint_z");
  requireSize(payload.spacePointR, nSpacePoints, "spacepoint_r");
  requireSize(payload.spacePointTimeValid, nSpacePoints,
              "spacepoint_time_valid");
  requireSize(payload.spacePointTime, nSpacePoints, "spacepoint_time");
  requireSize(payload.spacePointVarianceR, nSpacePoints,
              "spacepoint_variance_r");
  requireSize(payload.spacePointVarianceZ, nSpacePoints,
              "spacepoint_variance_z");
  requireSize(payload.spacePointSourceOffset, nSpacePoints + 1,
              "spacepoint_source_offset");
  require(payload.spacePointSourceOffset.front() == 0 &&
              payload.spacePointSourceOffset.back() ==
                  payload.spacePointSourceGeometryId.size() &&
              payload.spacePointSourceGeometryId.size() ==
                  payload.spacePointSourceMeasurementIndex.size(),
          "space-point source-link CSR mismatch");
  for (std::size_t index = 0; index < nSpacePoints; ++index) {
    require(payload.spacePointIndex[index] == index,
            "space-point indices must be ordered and contiguous");
    require(payload.spacePointKind[index] == 0 &&
                payload.spacePointOverlapClass[index] == 0,
            "non-pixel or overlap space point in pixel payload");
    require(payload.spacePointTimeValid[index] <= 1,
            "invalid space-point time marker");
    requireFinite(payload.spacePointX[index], "space-point x");
    requireFinite(payload.spacePointY[index], "space-point y");
    requireFinite(payload.spacePointZ[index], "space-point z");
    requireFinite(payload.spacePointR[index], "space-point r");
    requireFinite(payload.spacePointTime[index], "space-point time storage");
    requireFinite(payload.spacePointVarianceR[index],
                  "space-point variance R");
    requireFinite(payload.spacePointVarianceZ[index],
                  "space-point variance Z");
    require(payload.spacePointVarianceR[index] >= 0 &&
                payload.spacePointVarianceZ[index] >= 0,
            "negative space-point variance");
    require(payload.spacePointTimeValid[index] != 0 ||
                std::bit_cast<std::uint32_t>(
                    payload.spacePointTime[index]) == 0,
            "invalid-time space point does not store canonical +0");
    const std::size_t begin = payload.spacePointSourceOffset[index];
    const std::size_t end = payload.spacePointSourceOffset[index + 1];
    require(end >= begin && end - begin == 1,
            "pixel space point must have exactly one source link");
    const std::size_t measurement =
        payload.spacePointSourceMeasurementIndex[begin];
    require(measurement < nMeasurements,
            "space-point source measurement is unresolved");
    const std::uint64_t geometry =
        payload.spacePointSourceGeometryId[begin];
    require(geometry == payload.measurementGeometryId[measurement],
            "source-link and measurement geometry IDs differ");
    if (trackingGeometry != nullptr) {
      require(trackingGeometry->findSurface(Acts::GeometryIdentifier(geometry)) !=
                  nullptr,
              "unresolved source-link geometry ID");
    }
  }

  const std::size_t nParticles = payload.particleCount;
  requireSize(payload.particleBarcode, 5 * nParticles, "particle_barcode");
  requireSize(payload.particleBarcodeHash, nParticles,
              "particle_barcode_hash");
  requireSize(payload.particlePdg, nParticles, "particle_pdg");
  requireSize(payload.particleProcess, nParticles, "particle_process");
  requireSize(payload.particleCharge, nParticles, "particle_charge");
  requireSize(payload.particleMass, nParticles, "particle_mass");
  requireSize(payload.particleInitialPosition4, 4 * nParticles,
              "particle_initial_position4");
  requireSize(payload.particleInitialDirection3, 3 * nParticles,
              "particle_initial_direction3");
  requireSize(payload.particleInitialMomentum, nParticles,
              "particle_initial_momentum");
  requireSize(payload.particleInitialProperTime, nParticles,
              "particle_initial_proper_time");
  requireSize(payload.particleInitialPathInX0, nParticles,
              "particle_initial_path_in_x0");
  requireSize(payload.particleInitialPathInL0, nParticles,
              "particle_initial_path_in_l0");
  requireSize(payload.particleInitialNumberOfHits, nParticles,
              "particle_initial_number_of_hits");
  requireSize(payload.particleInitialOutcome, nParticles,
              "particle_initial_outcome");
  requireSize(payload.particleFinalPosition4, 4 * nParticles,
              "particle_final_position4");
  requireSize(payload.particleFinalDirection3, 3 * nParticles,
              "particle_final_direction3");
  requireSize(payload.particleFinalMomentum, nParticles,
              "particle_final_momentum");
  requireSize(payload.particleFinalProperTime, nParticles,
              "particle_final_proper_time");
  requireSize(payload.particleFinalPathInX0, nParticles,
              "particle_final_path_in_x0");
  requireSize(payload.particleFinalPathInL0, nParticles,
              "particle_final_path_in_l0");
  requireSize(payload.particleFinalNumberOfHits, nParticles,
              "particle_final_number_of_hits");
  requireSize(payload.particleFinalOutcome, nParticles,
              "particle_final_outcome");
  requireSize(payload.particleSelected, nParticles, "particle_selected");
  std::set<SimBarcode> particleIds;
  std::size_t selectedCount = 0;
  for (std::size_t index = 0; index < nParticles; ++index) {
    const SimBarcode barcode = barcodeAt(payload.particleBarcode, index);
    require(barcode.isValid(), "invalid particle barcode");
    require(particleIds.empty() || *particleIds.rbegin() < barcode,
            "particle barcodes duplicated or not ordered");
    particleIds.insert(barcode);
    require(payload.particleBarcodeHash[index] == barcode.hash(),
            "particle barcode hash mismatch");
    require(payload.particlePdg[index] !=
                static_cast<int>(Acts::PdgParticle::eInvalid),
            "invalid particle PDG code");
    require(payload.particleProcess[index] <=
                static_cast<unsigned int>(
                    ActsFatras::GenerationProcess::eNuclearInteraction),
            "particle generation process is out of range");
    require(payload.particleInitialOutcome[index] <=
                static_cast<unsigned int>(
                    ActsFatras::SimulationOutcome::KilledSecondaryParticle) &&
                payload.particleFinalOutcome[index] <=
                    static_cast<unsigned int>(ActsFatras::SimulationOutcome::
                                                  KilledSecondaryParticle),
            "particle simulation outcome is out of range");
    requireFinite(payload.particleCharge[index], "particle charge");
    requireFinite(payload.particleMass[index], "particle mass");
    require(payload.particleMass[index] >= 0, "negative particle mass");
    require(payload.particleSelected[index] <= 1,
            "invalid selected-particle marker");
    selectedCount += payload.particleSelected[index];
    for (std::size_t component = 0; component < 4; ++component) {
      requireFinite(payload.particleInitialPosition4[4 * index + component],
                    "particle initial position");
      requireFinite(payload.particleFinalPosition4[4 * index + component],
                    "particle final position");
    }
    double initialNorm = 0;
    double finalNorm = 0;
    for (std::size_t component = 0; component < 3; ++component) {
      const double initial =
          payload.particleInitialDirection3[3 * index + component];
      const double final =
          payload.particleFinalDirection3[3 * index + component];
      requireFinite(initial, "particle initial direction");
      requireFinite(final, "particle final direction");
      initialNorm += initial * initial;
      finalNorm += final * final;
    }
    constexpr double unitDirectionTolerance =
        64 * std::numeric_limits<double>::epsilon();
    require(std::isfinite(initialNorm) && std::isfinite(finalNorm) &&
                std::abs(initialNorm - 1.0) <= unitDirectionTolerance &&
                std::abs(finalNorm - 1.0) <= unitDirectionTolerance,
            "particle direction is not unit length");
    for (double scalar : {payload.particleInitialMomentum[index],
                          payload.particleInitialProperTime[index],
                          payload.particleInitialPathInX0[index],
                          payload.particleInitialPathInL0[index],
                          payload.particleFinalMomentum[index],
                          payload.particleFinalProperTime[index],
                          payload.particleFinalPathInX0[index],
                          payload.particleFinalPathInL0[index]}) {
      requireFinite(scalar, "particle state scalar");
    }
    require(payload.particleInitialMomentum[index] >= 0 &&
                payload.particleFinalMomentum[index] >= 0 &&
                payload.particleInitialPathInX0[index] >= 0 &&
                payload.particleInitialPathInL0[index] >= 0 &&
                payload.particleFinalPathInX0[index] >= 0 &&
                payload.particleFinalPathInL0[index] >= 0,
            "negative particle state scalar");
  }
  require(selectedCount == payload.selectedParticleCount,
          "selected-particle count mismatch");

  const std::size_t nForward = payload.measurementParticlesCount;
  requireSize(payload.measurementParticlesOrdinal, nForward,
              "measurement_particles_ordinal");
  requireSize(payload.measurementParticlesMeasurementIndex, nForward,
              "measurement_particles_measurement_index");
  requireSize(payload.measurementParticlesBarcode, 5 * nForward,
              "measurement_particles_barcode");
  std::vector<std::pair<std::size_t, SimBarcode>> forward;
  forward.reserve(nForward);
  for (std::size_t index = 0; index < nForward; ++index) {
    require(payload.measurementParticlesOrdinal[index] == index,
            "malformed forward relation ordinal");
    const std::size_t measurement =
        payload.measurementParticlesMeasurementIndex[index];
    const SimBarcode barcode =
        barcodeAt(payload.measurementParticlesBarcode, index);
    require(measurement < nMeasurements,
            "unresolved forward relation measurement");
    require(particleIds.contains(barcode),
            "unresolved forward relation particle");
    require(forward.empty() || forward.back().first <= measurement,
            "forward truth map order differs");
    forward.emplace_back(measurement, barcode);
  }

  const std::size_t nInverse = payload.particleMeasurementsCount;
  requireSize(payload.particleMeasurementsOrdinal, nInverse,
              "particle_measurements_ordinal");
  requireSize(payload.particleMeasurementsBarcode, 5 * nInverse,
              "particle_measurements_barcode");
  requireSize(payload.particleMeasurementsMeasurementIndex, nInverse,
              "particle_measurements_measurement_index");
  std::vector<std::pair<SimBarcode, std::size_t>> inverse;
  inverse.reserve(nInverse);
  for (std::size_t index = 0; index < nInverse; ++index) {
    require(payload.particleMeasurementsOrdinal[index] == index,
            "malformed inverse relation ordinal");
    const SimBarcode barcode =
        barcodeAt(payload.particleMeasurementsBarcode, index);
    const std::size_t measurement =
        payload.particleMeasurementsMeasurementIndex[index];
    require(particleIds.contains(barcode),
            "unresolved inverse relation particle");
    require(measurement < nMeasurements,
            "unresolved inverse relation measurement");
    const auto relation = std::pair{barcode, measurement};
    require(inverse.empty() || inverse.back() <= relation,
            "inverse truth map order differs");
    inverse.push_back(relation);
  }
  auto inverted = forward;
  std::vector<std::pair<SimBarcode, std::size_t>> normalizedForward;
  normalizedForward.reserve(inverted.size());
  for (const auto& [measurement, barcode] : inverted) {
    normalizedForward.emplace_back(barcode, measurement);
  }
  std::ranges::sort(normalizedForward);
  require(normalizedForward == inverse,
          "truth maps are not exact inverse multisets");

  const auto measurementsDigest = hashMeasurements(payload);
  const auto spacePointsDigest = hashSpacePoints(payload);
  const auto particlesDigest = hashParticles(payload);
  const auto selectedDigest = hashSelectedParticles(payload);
  const auto forwardDigest = hashMeasurementParticles(payload);
  const auto inverseDigest = hashParticleMeasurements(payload);
  std::array<std::array<std::uint8_t, 32>, 6> digests = {
      measurementsDigest, spacePointsDigest, particlesDigest,
      selectedDigest,     forwardDigest,     inverseDigest};

  Encoder eventEncoder;
  eventEncoder.text(kCanonicalStream);
  eventEncoder.text("event");
  eventEncoder.u64(payload.eventId);
  for (std::size_t index = 0; index < kSections.size(); ++index) {
    eventEncoder.text(kSections[index]);
    eventEncoder.digestBytes(digests[index]);
  }
  const auto eventDigest = eventEncoder.digest();

  OwnedSeedingEventSummary summary;
  summary.ordinal = payload.eventOrdinal;
  summary.eventId = payload.eventId;
  summary.measurements = payload.measurementCount;
  summary.spacePoints = payload.spacePointCount;
  summary.particles = payload.particleCount;
  summary.selectedParticles = payload.selectedParticleCount;
  summary.measurementParticles = payload.measurementParticlesCount;
  summary.particleMeasurements = payload.particleMeasurementsCount;
  summary.measurementsSha256 = hexDigest(measurementsDigest);
  summary.spacePointsSha256 = hexDigest(spacePointsDigest);
  summary.particlesSha256 = hexDigest(particlesDigest);
  summary.selectedParticlesSha256 = hexDigest(selectedDigest);
  summary.measurementParticlesSha256 = hexDigest(forwardDigest);
  summary.particleMeasurementsSha256 = hexDigest(inverseDigest);
  summary.semanticSha256 = hexDigest(eventDigest);
  return summary;
}

void setHashes(Payload& payload, const OwnedSeedingEventSummary& summary) {
  payload.measurementsSha256 = summary.measurementsSha256;
  payload.spacePointsSha256 = summary.spacePointsSha256;
  payload.particlesSha256 = summary.particlesSha256;
  payload.selectedParticlesSha256 = summary.selectedParticlesSha256;
  payload.measurementParticlesSha256 = summary.measurementParticlesSha256;
  payload.particleMeasurementsSha256 = summary.particleMeasurementsSha256;
  payload.eventSemanticSha256 = summary.semanticSha256;
}

void verifyStoredHashes(const Payload& payload,
                        const OwnedSeedingEventSummary& summary) {
  require(payload.measurementsSha256 == summary.measurementsSha256,
          "measurement semantic hash mismatch");
  require(payload.spacePointsSha256 == summary.spacePointsSha256,
          "space-point semantic hash mismatch");
  require(payload.particlesSha256 == summary.particlesSha256,
          "particle semantic hash mismatch");
  require(payload.selectedParticlesSha256 ==
              summary.selectedParticlesSha256,
          "selected-particle semantic hash mismatch");
  require(payload.measurementParticlesSha256 ==
              summary.measurementParticlesSha256,
          "forward truth-map semantic hash mismatch");
  require(payload.particleMeasurementsSha256 ==
              summary.particleMeasurementsSha256,
          "inverse truth-map semantic hash mismatch");
  require(payload.eventSemanticSha256 == summary.semanticSha256,
          "event semantic hash mismatch");
}

void bookBranches(TTree& tree, Payload& payload) {
  tree.Branch("event_ordinal", &payload.eventOrdinal);
  tree.Branch("event_id", &payload.eventId);
  tree.Branch("measurement_count", &payload.measurementCount);
  tree.Branch("spacepoint_count", &payload.spacePointCount);
  tree.Branch("particle_count", &payload.particleCount);
  tree.Branch("selected_particle_count", &payload.selectedParticleCount);
  tree.Branch("measurement_particles_count",
              &payload.measurementParticlesCount);
  tree.Branch("particle_measurements_count",
              &payload.particleMeasurementsCount);
#define BOOK_VECTOR(member, type, branch) tree.Branch(branch, &payload.member);
  OWNED_VECTOR_FIELDS(BOOK_VECTOR)
#undef BOOK_VECTOR
#define BOOK_STRING(member, branch) tree.Branch(branch, &payload.member);
  OWNED_STRING_FIELDS(BOOK_STRING)
#undef BOOK_STRING
}

std::set<std::string> requiredBranches() {
  std::set<std::string> names = {
      "event_ordinal", "event_id", "measurement_count", "spacepoint_count",
      "particle_count", "selected_particle_count",
      "measurement_particles_count", "particle_measurements_count"};
#define ADD_VECTOR(member, type, branch) names.emplace(branch);
  OWNED_VECTOR_FIELDS(ADD_VECTOR)
#undef ADD_VECTOR
#define ADD_STRING(member, branch) names.emplace(branch);
  OWNED_STRING_FIELDS(ADD_STRING)
#undef ADD_STRING
  return names;
}

void connectBranches(TTree& tree, Payload& payload, ReadPointers& pointers) {
  pointers.pointTo(payload);
  auto connect = [&](const char* name, auto* address) {
    require(tree.SetBranchAddress(name, address) >= 0,
            std::string("cannot connect ROOT branch ") + name);
  };
  connect("event_ordinal", &payload.eventOrdinal);
  connect("event_id", &payload.eventId);
  connect("measurement_count", &payload.measurementCount);
  connect("spacepoint_count", &payload.spacePointCount);
  connect("particle_count", &payload.particleCount);
  connect("selected_particle_count", &payload.selectedParticleCount);
  connect("measurement_particles_count", &payload.measurementParticlesCount);
  connect("particle_measurements_count", &payload.particleMeasurementsCount);
#define CONNECT_VECTOR(member, type, branch) connect(branch, &pointers.member);
  OWNED_VECTOR_FIELDS(CONNECT_VECTOR)
#undef CONNECT_VECTOR
#define CONNECT_STRING(member, branch) connect(branch, &pointers.member);
  OWNED_STRING_FIELDS(CONNECT_STRING)
#undef CONNECT_STRING
}

void validateBranchSet(TTree& tree) {
  std::set<std::string> actual;
  TObjArray* branches = tree.GetListOfBranches();
  require(branches != nullptr, "ROOT tree has no branch list");
  for (int index = 0; index < branches->GetEntries(); ++index) {
    TObject* branch = branches->At(index);
    require(branch != nullptr, "ROOT tree contains a null branch");
    actual.emplace(branch->GetName());
  }
  require(actual == requiredBranches(), "ROOT branch schema mismatch");
}

std::unique_ptr<TFile> openRootFile(const std::string& path,
                                    const char* mode) {
  TFile* raw = TFile::Open(path.c_str(), mode);
  if (raw == nullptr || raw->IsZombie()) {
    if (raw != nullptr) {
      raw->Close();
      delete raw;
    }
    throw std::ios_base::failure("could not open ROOT file '" + path + "'");
  }
  return std::unique_ptr<TFile>(raw);
}

void setCompression(TFile& file, const std::string& compression, int level) {
  require(level >= 0, "negative ROOT compression level");
  if (compression == "uncompressed") {
    require(level == 0, "uncompressed ROOT payload level must be zero");
    file.SetCompressionLevel(0);
  } else if (compression == "lz4") {
    file.SetCompressionSettings(ROOT::CompressionSettings(ROOT::kLZ4, level));
  } else if (compression == "zstd") {
    file.SetCompressionSettings(ROOT::CompressionSettings(ROOT::kZSTD, level));
  } else {
    throw std::invalid_argument("unsupported ROOT compression: " +
                                compression);
  }
}

bool sameBits(double lhs, double rhs) {
  return std::bit_cast<std::uint64_t>(lhs) ==
         std::bit_cast<std::uint64_t>(rhs);
}

SimParticleState restoreState(const Payload& payload, std::size_t index,
                              bool initial, SimBarcode barcode,
                              Acts::PdgParticle pdg, double charge,
                              double mass,
                              ActsFatras::GenerationProcess process) {
  const auto& position = initial ? payload.particleInitialPosition4
                                 : payload.particleFinalPosition4;
  const auto& direction = initial ? payload.particleInitialDirection3
                                  : payload.particleFinalDirection3;
  const auto& momentum = initial ? payload.particleInitialMomentum
                                 : payload.particleFinalMomentum;
  const auto& properTime = initial ? payload.particleInitialProperTime
                                   : payload.particleFinalProperTime;
  const auto& pathInX0 = initial ? payload.particleInitialPathInX0
                                 : payload.particleFinalPathInX0;
  const auto& pathInL0 = initial ? payload.particleInitialPathInL0
                                 : payload.particleFinalPathInL0;
  const auto& hits = initial ? payload.particleInitialNumberOfHits
                             : payload.particleFinalNumberOfHits;
  const auto& outcome = initial ? payload.particleInitialOutcome
                                : payload.particleFinalOutcome;

  SimParticleState state(barcode, pdg, charge, mass);
  state.setProcess(process);
  state.setPosition4(position[4 * index], position[4 * index + 1],
                     position[4 * index + 2], position[4 * index + 3]);
  const Acts::Vector3 validatedDirection(
      direction[3 * index], direction[3 * index + 1],
      direction[3 * index + 2]);
  OwnedSeedingParticleDirectionRestorer::restoreValidated(
      state, validatedDirection);
  state.setAbsoluteMomentum(momentum[index]);
  state.setProperTime(properTime[index]);
  state.setMaterialPassed(pathInX0[index], pathInL0[index]);
  state.setNumberOfHits(hits[index]);
  state.setOutcome(static_cast<ActsFatras::SimulationOutcome>(outcome[index]));

  for (std::size_t component = 0; component < 3; ++component) {
    require(sameBits(state.direction()[component],
                     direction[3 * index + component]),
            "particle direction cannot be reconstructed bit-exactly");
  }
  return state;
}

}  // namespace

struct OwnedSeedingDatasetWriter::Impl {
  std::unique_ptr<TFile> file;
  TTree* tree = nullptr;
  Payload payload;
  std::vector<OwnedSeedingEventSummary> summaries;
  std::string rootUuid;
};

OwnedSeedingDatasetWriter::OwnedSeedingDatasetWriter(
    const Config& config, Acts::Logging::Level level)
    : m_cfg(config),
      m_logger(Acts::getDefaultLogger(name(), level)),
      m_impl(std::make_unique<Impl>()) {
  require(!m_cfg.filePath.empty(), "writer file path is empty");
  require(!m_cfg.treeName.empty(), "writer tree name is empty");
  m_inputMeasurements.initialize(m_cfg.inputMeasurements);
  m_inputSpacePoints.initialize(m_cfg.inputSpacePoints);
  m_inputParticles.initialize(m_cfg.inputParticles);
  m_inputSelectedParticles.initialize(m_cfg.inputSelectedParticles);
  m_inputMeasurementParticlesMap.initialize(
      m_cfg.inputMeasurementParticlesMap);
  m_inputParticleMeasurementsMap.initialize(m_cfg.inputParticleMeasurementsMap);

  m_impl->file = openRootFile(m_cfg.filePath, "CREATE");
  setCompression(*m_impl->file, m_cfg.compression, m_cfg.compressionLevel);
  m_impl->file->cd();
  m_impl->tree = new TTree(m_cfg.treeName.c_str(),
                           "Owned ACTS seeding dataset v1 events");
  require(m_impl->tree != nullptr, "could not create ROOT tree");
  bookBranches(*m_impl->tree, m_impl->payload);
}

OwnedSeedingDatasetWriter::~OwnedSeedingDatasetWriter() {
  if (m_impl != nullptr && m_impl->file != nullptr && m_impl->file->IsOpen()) {
    m_impl->file->Close();
  }
}

ProcessCode OwnedSeedingDatasetWriter::initialize() {
  return ProcessCode::SUCCESS;
}

ProcessCode OwnedSeedingDatasetWriter::write(
    const AlgorithmContext& context) {
  const auto& measurements = m_inputMeasurements(context);
  const auto& spacePoints = m_inputSpacePoints(context);
  const auto& particles = m_inputParticles(context);
  const auto& selectedParticles = m_inputSelectedParticles(context);
  const auto& forwardMap = m_inputMeasurementParticlesMap(context);
  const auto& inverseMap = m_inputParticleMeasurementsMap(context);

  std::lock_guard<std::mutex> lock(m_mutex);
  require(!m_finalized, "writer called after finalize");
  Payload& payload = m_impl->payload;
  payload.clear();
  payload.eventOrdinal = m_impl->summaries.size();
  payload.eventId = context.eventNumber;
  require(payload.eventOrdinal == payload.eventId,
          "writer events must be ordered and contiguous");

  payload.measurementCount = measurements.size();
  payload.measurementValueOffset.push_back(0);
  payload.measurementCovarianceOffset.push_back(0);
  for (std::size_t index = 0; index < measurements.size(); ++index) {
    const auto measurement = measurements.getMeasurement(index);
    payload.measurementIndex.push_back(index);
    payload.measurementGeometryId.push_back(measurement.geometryId().value());
    payload.measurementSize.push_back(measurement.size());
    for (std::size_t component = 0; component < measurement.size();
         ++component) {
      payload.measurementSubspaceIndex.push_back(
          measurement.subspaceIndexVector()[component]);
      payload.measurementParameter.push_back(
          measurement.parameters()[component]);
    }
    for (std::size_t row = 0; row < measurement.size(); ++row) {
      for (std::size_t column = 0; column < measurement.size(); ++column) {
        payload.measurementCovariance.push_back(
            measurement.covariance()(row, column));
      }
    }
    payload.measurementValueOffset.push_back(
        payload.measurementParameter.size());
    payload.measurementCovarianceOffset.push_back(
        payload.measurementCovariance.size());
  }

  payload.spacePointCount = spacePoints.size();
  payload.spacePointSourceOffset.push_back(0);
  for (const auto& spacePoint : spacePoints) {
    payload.spacePointIndex.push_back(spacePoint.index());
    payload.spacePointKind.push_back(0);
    payload.spacePointOverlapClass.push_back(0);
    payload.spacePointX.push_back(spacePoint.x());
    payload.spacePointY.push_back(spacePoint.y());
    payload.spacePointZ.push_back(spacePoint.z());
    payload.spacePointR.push_back(spacePoint.r());
    const bool validTime = !std::isnan(spacePoint.time());
    payload.spacePointTimeValid.push_back(validTime);
    payload.spacePointTime.push_back(validTime ? spacePoint.time() : 0.0f);
    payload.spacePointVarianceR.push_back(spacePoint.varianceR());
    payload.spacePointVarianceZ.push_back(spacePoint.varianceZ());
    for (const Acts::SourceLink& sourceLink : spacePoint.sourceLinks()) {
      const IndexSourceLink* indexSourceLink =
          sourceLink.getPtr<IndexSourceLink>();
      require(indexSourceLink != nullptr, "non-IndexSourceLink space point");
      payload.spacePointSourceGeometryId.push_back(
          indexSourceLink->geometryId().value());
      payload.spacePointSourceMeasurementIndex.push_back(
          indexSourceLink->index());
    }
    payload.spacePointSourceOffset.push_back(
        payload.spacePointSourceGeometryId.size());
  }

  std::set<SimBarcode> selectedIds;
  for (const SimParticle& particle : selectedParticles) {
    require(selectedIds.insert(particle.particleId()).second,
            "duplicate selected particle");
  }
  payload.particleCount = particles.size();
  for (const SimParticle& particle : particles) {
    const SimBarcode barcode = particle.particleId();
    appendBarcode(payload.particleBarcode, barcode);
    payload.particleBarcodeHash.push_back(barcode.hash());
    payload.particlePdg.push_back(static_cast<int>(particle.pdg()));
    payload.particleProcess.push_back(
        static_cast<unsigned int>(particle.process()));
    payload.particleCharge.push_back(particle.charge());
    payload.particleMass.push_back(particle.mass());
    appendState(payload, particle.initialState(), true);
    appendState(payload, particle.finalState(), false);
    payload.particleSelected.push_back(selectedIds.contains(barcode));
  }
  for (SimBarcode selected : selectedIds) {
    require(particles.find(selected) != particles.end(),
            "selected particle is absent from all particles");
  }
  payload.selectedParticleCount = selectedIds.size();

  payload.measurementParticlesCount = forwardMap.size();
  std::size_t ordinal = 0;
  for (const auto& [measurement, barcode] : forwardMap) {
    payload.measurementParticlesOrdinal.push_back(ordinal++);
    payload.measurementParticlesMeasurementIndex.push_back(measurement);
    appendBarcode(payload.measurementParticlesBarcode, barcode);
  }
  payload.particleMeasurementsCount = inverseMap.size();
  ordinal = 0;
  for (const auto& [barcode, measurement] : inverseMap) {
    payload.particleMeasurementsOrdinal.push_back(ordinal++);
    appendBarcode(payload.particleMeasurementsBarcode, barcode);
    payload.particleMeasurementsMeasurementIndex.push_back(measurement);
  }

  OwnedSeedingEventSummary summary = validateAndHash(payload, nullptr);
  setHashes(payload, summary);
  require(m_impl->tree->Fill() > 0, "ROOT tree Fill failed");
  m_impl->summaries.push_back(std::move(summary));
  return ProcessCode::SUCCESS;
}

ProcessCode OwnedSeedingDatasetWriter::finalize() {
  std::lock_guard<std::mutex> lock(m_mutex);
  require(!m_finalized, "writer finalized twice");
  require(!m_impl->summaries.empty(), "cannot finalize an empty payload");
  m_impl->file->cd();
  require(m_impl->tree->Write("", TObject::kOverwrite) > 0,
          "ROOT tree Write failed");
  require(m_impl->file->Write("", TObject::kOverwrite) >= 0,
          "ROOT file Write failed");
  m_impl->rootUuid = m_impl->file->GetUUID().AsString();
  m_impl->file->Close();
  require(!m_impl->rootUuid.empty(), "ROOT UUID is empty");
  m_finalized = true;
  return ProcessCode::SUCCESS;
}

std::vector<OwnedSeedingEventSummary>
OwnedSeedingDatasetWriter::summaries() const {
  std::lock_guard<std::mutex> lock(m_mutex);
  require(m_finalized, "summaries requested before finalize");
  return m_impl->summaries;
}

std::string OwnedSeedingDatasetWriter::rootUuid() const {
  std::lock_guard<std::mutex> lock(m_mutex);
  require(m_finalized, "ROOT UUID requested before finalize");
  return m_impl->rootUuid;
}

OwnedSeedingDiagnosticsWriter::OwnedSeedingDiagnosticsWriter(
    const Config& config, Acts::Logging::Level level)
    : m_cfg(config), m_logger(Acts::getDefaultLogger(name(), level)) {
  m_inputRawSeeds.initialize(m_cfg.inputRawSeeds);
  m_inputEstimatedSeeds.initialize(m_cfg.inputEstimatedSeeds);
  m_inputEstimatedParameters.initialize(m_cfg.inputEstimatedParameters);
  m_inputTracks.initialize(m_cfg.inputTracks);
  m_inputTrackParticleMatching.initialize(m_cfg.inputTrackParticleMatching);
  m_inputParticleTrackMatching.initialize(m_cfg.inputParticleTrackMatching);
}

ProcessCode OwnedSeedingDiagnosticsWriter::write(
    const AlgorithmContext& context) {
  const auto& rawSeeds = m_inputRawSeeds(context);
  const auto& estimatedSeeds = m_inputEstimatedSeeds(context);
  const auto& parameters = m_inputEstimatedParameters(context);
  const auto& tracks = m_inputTracks(context);
  const auto& trackMatching = m_inputTrackParticleMatching(context);
  const auto& particleMatching = m_inputParticleTrackMatching(context);

  require(estimatedSeeds.size() == parameters.size(),
          "estimated seed and parameter counts differ");
  require(tracks.size() == estimatedSeeds.size(),
          "converted track and estimated seed counts differ");

  Encoder encoder;
  encoder.text(kCanonicalStream);
  encoder.text("seeding_diagnostics");
  encoder.u64(context.eventNumber);

  const auto encodeSeeds = [&](std::string_view tag,
                               const SeedContainer& seeds) {
    encoder.text(tag);
    encoder.u64(seeds.size());
    for (const auto& seed : seeds) {
      const auto points = seed.spacePoints();
      require(points.size() == 3,
              "diagnostic seed does not contain exactly three points");
      encoder.u64(points.size());
      for (const auto& point : points) {
        require(point.sourceLinks().size() == 1,
                "diagnostic seed point does not have one source link");
        const auto* source =
            point.sourceLinks()[0].getPtr<IndexSourceLink>();
        require(source != nullptr,
                "diagnostic seed point has a non-index source link");
        encoder.u64(source->geometryId().value());
        encoder.u64(source->index());
        encoder.u32(point.index());
      }
      encoder.f64(seed.vertexZ());
      encoder.f32(seed.quality());
    }
  };
  encodeSeeds("raw_seeds", rawSeeds);
  encodeSeeds("estimated_seeds", estimatedSeeds);

  encoder.text("estimated_parameters");
  encoder.u64(parameters.size());
  for (const TrackParameters& parameter : parameters) {
    encoder.u64(parameter.referenceSurface().geometryId().value());
    for (double value : parameter.parameters()) {
      requireFinite(value, "estimated track parameter");
      encoder.f64(value);
    }
    encoder.u8(parameter.covariance().has_value());
    if (parameter.covariance().has_value()) {
      for (std::size_t row = 0; row < Acts::eBoundSize; ++row) {
        for (std::size_t column = 0; column < Acts::eBoundSize; ++column) {
          const double value = (*parameter.covariance())(row, column);
          requireFinite(value, "estimated track covariance");
          encoder.f64(value);
        }
      }
    }
    const Acts::ParticleHypothesis& hypothesis =
        parameter.particleHypothesis();
    encoder.i32(static_cast<std::int32_t>(hypothesis.absolutePdg()));
    encoder.f32(hypothesis.mass());
    encoder.f32(hypothesis.absoluteCharge());
  }

  encoder.text("converted_tracks");
  encoder.u64(tracks.size());
  for (const auto& track : tracks) {
    encoder.u64(track.index());
    encoder.u32(track.nMeasurements());
    encoder.u32(track.nOutliers());
    encoder.u32(track.nHoles());
    std::uint64_t stateCount = 0;
    for ([[maybe_unused]] const auto& state : track.trackStatesReversed()) {
      ++stateCount;
    }
    encoder.u64(stateCount);
    for (const auto& state : track.trackStatesReversed()) {
      require(state.hasUncalibratedSourceLink(),
              "converted track state lacks a source link");
      const Acts::SourceLink sourceLink = state.getUncalibratedSourceLink();
      const auto* source = sourceLink.getPtr<IndexSourceLink>();
      require(source != nullptr,
              "converted track has a non-index source link");
      encoder.u64(source->geometryId().value());
      encoder.u64(source->index());
    }
  }

  OwnedSeedingDiagnosticsSummary summary;
  summary.eventId = context.eventNumber;
  summary.rawSeeds = rawSeeds.size();
  summary.estimatedSeeds = estimatedSeeds.size();
  summary.estimatedParameters = parameters.size();
  summary.convertedTracks = tracks.size();

  encoder.text("track_particle_matching");
  encoder.u64(trackMatching.size());
  require(trackMatching.size() <= tracks.size(),
          "matcher produced more rows than converted tracks");
  summary.unknownTracks = tracks.size() - trackMatching.size();
  for (const auto& [trackIndex, match] : trackMatching) {
    encoder.u64(trackIndex);
    encoder.u32(static_cast<std::uint32_t>(match.classification));
    switch (match.classification) {
      case TrackMatchClassification::Matched:
        ++summary.matchedTracks;
        break;
      case TrackMatchClassification::Fake:
        ++summary.fakeTracks;
        break;
      case TrackMatchClassification::Duplicate:
        ++summary.duplicateTracks;
        break;
      case TrackMatchClassification::Unknown:
        ++summary.unknownTracks;
        break;
    }
    encoder.u8(match.particle.has_value());
    if (match.particle.has_value()) {
      encodeBarcode(encoder, *match.particle);
    }
    encoder.u64(match.contributingParticles.size());
    for (const ParticleHitCount& contribution : match.contributingParticles) {
      encodeBarcode(encoder, contribution.particleId);
      encoder.u64(contribution.hitCount);
    }
  }

  encoder.text("particle_track_matching");
  encoder.u64(particleMatching.size());
  for (const auto& [barcode, match] : particleMatching) {
    encodeBarcode(encoder, barcode);
    encoder.u8(match.track.has_value());
    if (match.track.has_value()) {
      encoder.u64(*match.track);
    }
    encoder.u32(match.duplicates);
    encoder.u32(match.fakes);
  }
  summary.semanticSha256 = hexDigest(encoder.digest());

  std::lock_guard<std::mutex> lock(m_mutex);
  require(m_summaries.size() == context.eventNumber,
          "diagnostic events must be ordered and contiguous");
  m_summaries.push_back(std::move(summary));
  return ProcessCode::SUCCESS;
}

std::vector<OwnedSeedingDiagnosticsSummary>
OwnedSeedingDiagnosticsWriter::summaries() const {
  std::lock_guard<std::mutex> lock(m_mutex);
  return m_summaries;
}

struct OwnedSeedingDatasetReader::Impl {
  std::unique_ptr<TFile> file;
  TTree* tree = nullptr;
  Payload payload;
  ReadPointers pointers;
};

OwnedSeedingDatasetReader::OwnedSeedingDatasetReader(
    const Config& config, Acts::Logging::Level level)
    : m_cfg(config),
      m_logger(Acts::getDefaultLogger(name(), level)),
      m_impl(std::make_unique<Impl>()) {
  require(!m_cfg.filePath.empty(), "reader file path is empty");
  require(!m_cfg.treeName.empty(), "reader tree name is empty");
  require(m_cfg.trackingGeometry != nullptr,
          "reader tracking geometry is missing");
  require(!m_cfg.expectedEventIds.empty(), "reader expected event list is empty");
  require(m_cfg.expectedEventIds.size() == m_cfg.expectedEventHashes.size(),
          "reader expected event/hash sizes differ");

  m_outputMeasurements.initialize(m_cfg.outputMeasurements);
  m_outputMeasurementSubset.initialize(m_cfg.outputMeasurementSubset);
  m_outputSpacePoints.initialize(m_cfg.outputSpacePoints);
  m_outputParticles.initialize(m_cfg.outputParticles);
  m_outputSelectedParticles.initialize(m_cfg.outputSelectedParticles);
  m_outputMeasurementParticlesMap.initialize(
      m_cfg.outputMeasurementParticlesMap);
  m_outputParticleMeasurementsMap.initialize(
      m_cfg.outputParticleMeasurementsMap);

  m_impl->file = openRootFile(m_cfg.filePath, "READ");
  TObject* object = m_impl->file->Get(m_cfg.treeName.c_str());
  m_impl->tree = dynamic_cast<TTree*>(object);
  require(m_impl->tree != nullptr, "payload event tree is missing");
  validateBranchSet(*m_impl->tree);
  require(static_cast<std::size_t>(m_impl->tree->GetEntries()) ==
              m_cfg.expectedEventIds.size(),
          "missing or extra ROOT event entries");
  connectBranches(*m_impl->tree, m_impl->payload, m_impl->pointers);

  m_impl->tree->SetBranchStatus("*", false);
  for (const char* branch : {"event_ordinal", "event_id",
                             "event_semantic_sha256", "measurement_count",
                             "spacepoint_count", "particle_count",
                             "selected_particle_count",
                             "measurement_particles_count",
                             "particle_measurements_count"}) {
    m_impl->tree->SetBranchStatus(branch, true);
  }
  std::set<std::uint64_t> observed;
  for (std::size_t ordinal = 0; ordinal < m_cfg.expectedEventIds.size();
       ++ordinal) {
    require(m_impl->tree->GetEntry(ordinal) > 0,
            "could not read ROOT event header");
    require(m_impl->payload.eventOrdinal == ordinal,
            "duplicate or reordered ROOT event ordinal");
    require(m_impl->payload.eventId == m_cfg.expectedEventIds[ordinal],
            "missing, duplicate, or reordered ROOT event ID");
    require(observed.insert(m_impl->payload.eventId).second,
            "duplicate ROOT event ID");
    require(m_impl->payload.eventSemanticSha256 ==
                m_cfg.expectedEventHashes[ordinal],
            "ROOT event header hash differs from manifest");
  }
  m_impl->tree->SetBranchStatus("*", true);
  m_impl->payload.clear();
}

OwnedSeedingDatasetReader::~OwnedSeedingDatasetReader() {
  if (m_impl != nullptr && m_impl->file != nullptr && m_impl->file->IsOpen()) {
    m_impl->file->Close();
  }
}

std::pair<std::size_t, std::size_t>
OwnedSeedingDatasetReader::availableEvents() const {
  return {0, m_cfg.expectedEventIds.size()};
}

ProcessCode OwnedSeedingDatasetReader::read(
    const AlgorithmContext& context) {
  std::lock_guard<std::mutex> lock(m_mutex);
  const std::size_t ordinal = context.eventNumber;
  require(ordinal < m_cfg.expectedEventIds.size(),
          "requested event is outside manifest range");
  require(m_impl->tree->GetEntry(ordinal) > 0, "could not read ROOT event");
  Payload& payload = m_impl->payload;
  require(payload.eventOrdinal == ordinal &&
              payload.eventId == m_cfg.expectedEventIds[ordinal],
          "ROOT event identity changed after preflight");
  OwnedSeedingEventSummary summary =
      validateAndHash(payload, m_cfg.trackingGeometry.get());
  verifyStoredHashes(payload, summary);
  require(summary.semanticSha256 == m_cfg.expectedEventHashes[ordinal],
          "recomputed event hash differs from manifest");

  MeasurementContainer measurements;
  measurements.reserve(payload.measurementCount);
  for (std::size_t index = 0; index < payload.measurementCount; ++index) {
    const std::size_t size = payload.measurementSize[index];
    auto measurement = measurements.makeMeasurement(
        size, Acts::GeometryIdentifier(payload.measurementGeometryId[index]));
    std::vector<std::uint8_t> subspace(size);
    Eigen::VectorXd parameters(size);
    Eigen::MatrixXd covariance(size, size);
    const std::size_t valueBegin = payload.measurementValueOffset[index];
    const std::size_t covarianceBegin =
        payload.measurementCovarianceOffset[index];
    for (std::size_t component = 0; component < size; ++component) {
      subspace[component] =
          payload.measurementSubspaceIndex[valueBegin + component];
      parameters[component] =
          payload.measurementParameter[valueBegin + component];
    }
    for (std::size_t row = 0; row < size; ++row) {
      for (std::size_t column = 0; column < size; ++column) {
        covariance(row, column) = payload.measurementCovariance[
            covarianceBegin + row * size + column];
      }
    }
    measurement.fill(subspace, parameters, covariance);
  }

  SpacePointContainer spacePoints(
      SpacePointColumns::SourceLinks | SpacePointColumns::X |
      SpacePointColumns::Y | SpacePointColumns::Z | SpacePointColumns::R |
      SpacePointColumns::Time | SpacePointColumns::VarianceZ |
      SpacePointColumns::VarianceR | SpacePointColumns::Strip);
  spacePoints.reserve(payload.spacePointCount, 1.0f);
  for (std::size_t index = 0; index < payload.spacePointCount; ++index) {
    auto spacePoint = spacePoints.createSpacePoint();
    const std::size_t sourceOffset = payload.spacePointSourceOffset[index];
    const IndexSourceLink sourceLink(
        Acts::GeometryIdentifier(
            payload.spacePointSourceGeometryId[sourceOffset]),
        payload.spacePointSourceMeasurementIndex[sourceOffset]);
    const std::array sourceLinks{Acts::SourceLink(sourceLink)};
    spacePoint.assignSourceLinks(sourceLinks);
    spacePoint.x() = payload.spacePointX[index];
    spacePoint.y() = payload.spacePointY[index];
    spacePoint.z() = payload.spacePointZ[index];
    spacePoint.r() = payload.spacePointR[index];
    spacePoint.time() = payload.spacePointTimeValid[index]
                            ? payload.spacePointTime[index]
                            : Acts::NoTime;
    spacePoint.varianceR() = payload.spacePointVarianceR[index];
    spacePoint.varianceZ() = payload.spacePointVarianceZ[index];
  }

  SimParticleContainer particles;
  SimParticleContainer selectedParticles;
  for (std::size_t index = 0; index < payload.particleCount; ++index) {
    const SimBarcode barcode = barcodeAt(payload.particleBarcode, index);
    const auto pdg = static_cast<Acts::PdgParticle>(payload.particlePdg[index]);
    const auto process = static_cast<ActsFatras::GenerationProcess>(
        payload.particleProcess[index]);
    SimParticleState initial = restoreState(
        payload, index, true, barcode, pdg, payload.particleCharge[index],
        payload.particleMass[index], process);
    SimParticleState final = restoreState(
        payload, index, false, barcode, pdg, payload.particleCharge[index],
        payload.particleMass[index], process);
    SimParticle particle(initial, final);
    particles.insert(particle);
    if (payload.particleSelected[index] != 0) {
      selectedParticles.insert(particle);
    }
  }

  MeasurementParticlesMap forwardMap;
  for (std::size_t index = 0; index < payload.measurementParticlesCount;
       ++index) {
    forwardMap.emplace_hint(
        forwardMap.end(), payload.measurementParticlesMeasurementIndex[index],
        barcodeAt(payload.measurementParticlesBarcode, index));
  }
  ParticleMeasurementsMap inverseMap;
  for (std::size_t index = 0; index < payload.particleMeasurementsCount;
       ++index) {
    inverseMap.emplace_hint(
        inverseMap.end(), barcodeAt(payload.particleMeasurementsBarcode, index),
        payload.particleMeasurementsMeasurementIndex[index]);
  }
  require(forwardMap.size() == payload.measurementParticlesCount &&
              inverseMap.size() == payload.particleMeasurementsCount,
          "truth map reconstruction lost multiplicity");

  // All validation and reconstruction completes before the first WhiteBoard
  // publication. DataHandle graph validation guarantees these keys are unique.
  const MeasurementContainer& storedMeasurements =
      m_outputMeasurements(context, std::move(measurements));
  std::vector<MeasurementContainer::Index> allIndices(
      storedMeasurements.size());
  std::iota(allIndices.begin(), allIndices.end(), Index{0});
  m_outputMeasurementSubset(
      context, MeasurementSubset(storedMeasurements, std::move(allIndices)));
  m_outputSpacePoints(context, std::move(spacePoints));
  m_outputParticles(context, std::move(particles));
  m_outputSelectedParticles(context, std::move(selectedParticles));
  m_outputMeasurementParticlesMap(context, std::move(forwardMap));
  m_outputParticleMeasurementsMap(context, std::move(inverseMap));

  m_completedEventIds.push_back(payload.eventId);
  m_completedEventHashes.push_back(summary.semanticSha256);
  return ProcessCode::SUCCESS;
}

std::vector<std::uint64_t>
OwnedSeedingDatasetReader::completedEventIds() const {
  std::lock_guard<std::mutex> lock(m_mutex);
  return m_completedEventIds;
}

std::vector<std::string>
OwnedSeedingDatasetReader::completedEventHashes() const {
  std::lock_guard<std::mutex> lock(m_mutex);
  return m_completedEventHashes;
}

}  // namespace ActsExamples
