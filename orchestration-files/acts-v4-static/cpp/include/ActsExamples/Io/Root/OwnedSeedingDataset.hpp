// This file is part of the autoresearch ACTS seeding project.
//
// It is an isolated qualification overlay for ACTS v46.5.0. It is not part of
// the upstream ACTS source tree and does not define a production dataset.

#pragma once

#include "Acts/Geometry/TrackingGeometry.hpp"
#include "Acts/Utilities/Logger.hpp"
#include "ActsExamples/EventData/Measurement.hpp"
#include "ActsExamples/EventData/Seed.hpp"
#include "ActsExamples/EventData/SimParticle.hpp"
#include "ActsExamples/EventData/SpacePoint.hpp"
#include "ActsExamples/EventData/Track.hpp"
#include "ActsExamples/EventData/TruthMatching.hpp"
#include "ActsExamples/Framework/DataHandle.hpp"
#include "ActsExamples/Framework/IReader.hpp"
#include "ActsExamples/Framework/IWriter.hpp"
#include "ActsExamples/Framework/ProcessCode.hpp"

#include <cstddef>
#include <cstdint>
#include <memory>
#include <mutex>
#include <string>
#include <utility>
#include <vector>

namespace ActsExamples {

/// Counts and semantic hashes for one event entry in an owned v1 payload.
struct OwnedSeedingEventSummary {
  std::uint32_t ordinal = 0;
  std::uint64_t eventId = 0;
  std::uint64_t measurements = 0;
  std::uint64_t spacePoints = 0;
  std::uint64_t particles = 0;
  std::uint64_t selectedParticles = 0;
  std::uint64_t measurementParticles = 0;
  std::uint64_t particleMeasurements = 0;
  std::string measurementsSha256;
  std::string spacePointsSha256;
  std::string particlesSha256;
  std::string selectedParticlesSha256;
  std::string measurementParticlesSha256;
  std::string particleMeasurementsSha256;
  std::string semanticSha256;
};

/// Write the exact post-digitization, post-pixel-SpacePointMaker seam.
///
/// The payload contains one ROOT tree entry per event and only primitive scalar
/// or vector branches. The writer rejects malformed seam data rather than
/// normalizing it. Calls are serialized even though static-v4 uses one thread.
class OwnedSeedingDatasetWriter final : public IWriter {
 public:
  struct Config {
    std::string inputMeasurements = "measurements";
    std::string inputSpacePoints = "spacepoints";
    std::string inputParticles = "particles_simulated";
    std::string inputSelectedParticles = "particles_selected";
    std::string inputMeasurementParticlesMap = "measurement_particles_map";
    std::string inputParticleMeasurementsMap = "particle_measurements_map";
    std::string filePath;
    std::string treeName = "events";
    std::string compression = "lz4";
    int compressionLevel = 4;
  };

  OwnedSeedingDatasetWriter(const Config& config, Acts::Logging::Level level);
  ~OwnedSeedingDatasetWriter() override;

  std::string name() const override { return "OwnedSeedingDatasetWriter"; }
  ProcessCode initialize() override;
  ProcessCode write(const AlgorithmContext& context) override;
  ProcessCode finalize() override;

  const Config& config() const { return m_cfg; }
  std::vector<OwnedSeedingEventSummary> summaries() const;
  std::string rootUuid() const;

 private:
  struct Impl;
  Config m_cfg;
  std::unique_ptr<const Acts::Logger> m_logger;
  std::unique_ptr<Impl> m_impl;
  mutable std::mutex m_mutex;
  bool m_finalized = false;

  ReadDataHandle<MeasurementContainer> m_inputMeasurements{this,
                                                           "InputMeasurements"};
  ReadDataHandle<SpacePointContainer> m_inputSpacePoints{this,
                                                         "InputSpacePoints"};
  ReadDataHandle<SimParticleContainer> m_inputParticles{this,
                                                        "InputParticles"};
  ReadDataHandle<SimParticleContainer> m_inputSelectedParticles{
      this, "InputSelectedParticles"};
  ReadDataHandle<MeasurementParticlesMap> m_inputMeasurementParticlesMap{
      this, "InputMeasurementParticlesMap"};
  ReadDataHandle<ParticleMeasurementsMap> m_inputParticleMeasurementsMap{
      this, "InputParticleMeasurementsMap"};
};

/// Exact ordered downstream diagnostics for generated/static equality gates.
struct OwnedSeedingDiagnosticsSummary {
  std::uint64_t eventId = 0;
  std::uint64_t rawSeeds = 0;
  std::uint64_t estimatedSeeds = 0;
  std::uint64_t estimatedParameters = 0;
  std::uint64_t convertedTracks = 0;
  std::uint64_t matchedTracks = 0;
  std::uint64_t fakeTracks = 0;
  std::uint64_t duplicateTracks = 0;
  std::uint64_t unknownTracks = 0;
  std::string semanticSha256;
};

/// Collect an exact semantic digest after estimation, conversion, and matching.
class OwnedSeedingDiagnosticsWriter final : public IWriter {
 public:
  struct Config {
    std::string inputRawSeeds = "seeds";
    std::string inputEstimatedSeeds = "estimatedseeds";
    std::string inputEstimatedParameters = "estimatedparameters";
    std::string inputTracks = "seed-tracks";
    std::string inputTrackParticleMatching = "seed_particle_matching";
    std::string inputParticleTrackMatching = "particle_seed_matching";
  };

  OwnedSeedingDiagnosticsWriter(const Config& config,
                                Acts::Logging::Level level);
  ~OwnedSeedingDiagnosticsWriter() override = default;

  std::string name() const override { return "OwnedSeedingDiagnosticsWriter"; }
  ProcessCode initialize() override { return ProcessCode::SUCCESS; }
  ProcessCode write(const AlgorithmContext& context) override;
  ProcessCode finalize() override { return ProcessCode::SUCCESS; }

  const Config& config() const { return m_cfg; }
  std::vector<OwnedSeedingDiagnosticsSummary> summaries() const;

 private:
  Config m_cfg;
  std::unique_ptr<const Acts::Logger> m_logger;
  mutable std::mutex m_mutex;
  std::vector<OwnedSeedingDiagnosticsSummary> m_summaries;

  ReadDataHandle<SeedContainer> m_inputRawSeeds{this, "InputRawSeeds"};
  ReadDataHandle<SeedContainer> m_inputEstimatedSeeds{this,
                                                      "InputEstimatedSeeds"};
  ReadDataHandle<TrackParametersContainer> m_inputEstimatedParameters{
      this, "InputEstimatedParameters"};
  ReadDataHandle<ConstTrackContainer> m_inputTracks{this, "InputTracks"};
  ReadDataHandle<TrackParticleMatching> m_inputTrackParticleMatching{
      this, "InputTrackParticleMatching"};
  ReadDataHandle<ParticleTrackMatching> m_inputParticleTrackMatching{
      this, "InputParticleTrackMatching"};
};

/// Read and validate an owned v1 payload before publishing event collections.
class OwnedSeedingDatasetReader final : public IReader {
 public:
  struct Config {
    std::string filePath;
    std::string treeName = "events";
    std::string outputMeasurements = "measurements";
    std::string outputMeasurementSubset = "measurement_subset";
    std::string outputSpacePoints = "spacepoints";
    std::string outputParticles = "particles_simulated";
    std::string outputSelectedParticles = "particles_selected";
    std::string outputMeasurementParticlesMap = "measurement_particles_map";
    std::string outputParticleMeasurementsMap = "particle_measurements_map";
    std::vector<std::uint64_t> expectedEventIds;
    std::vector<std::string> expectedEventHashes;
    std::shared_ptr<const Acts::TrackingGeometry> trackingGeometry;
  };

  OwnedSeedingDatasetReader(const Config& config, Acts::Logging::Level level);
  ~OwnedSeedingDatasetReader() override;

  std::string name() const override { return "OwnedSeedingDatasetReader"; }
  std::pair<std::size_t, std::size_t> availableEvents() const override;
  ProcessCode read(const AlgorithmContext& context) override;

  const Config& config() const { return m_cfg; }
  std::vector<std::uint64_t> completedEventIds() const;
  std::vector<std::string> completedEventHashes() const;

 private:
  struct Impl;
  Config m_cfg;
  std::unique_ptr<const Acts::Logger> m_logger;
  std::unique_ptr<Impl> m_impl;
  mutable std::mutex m_mutex;
  std::vector<std::uint64_t> m_completedEventIds;
  std::vector<std::string> m_completedEventHashes;

  WriteDataHandle<MeasurementContainer> m_outputMeasurements{
      this, "OutputMeasurements"};
  WriteDataHandle<MeasurementSubset> m_outputMeasurementSubset{
      this, "OutputMeasurementSubset"};
  WriteDataHandle<SpacePointContainer> m_outputSpacePoints{this,
                                                           "OutputSpacePoints"};
  WriteDataHandle<SimParticleContainer> m_outputParticles{this,
                                                          "OutputParticles"};
  WriteDataHandle<SimParticleContainer> m_outputSelectedParticles{
      this, "OutputSelectedParticles"};
  WriteDataHandle<MeasurementParticlesMap> m_outputMeasurementParticlesMap{
      this, "OutputMeasurementParticlesMap"};
  WriteDataHandle<ParticleMeasurementsMap> m_outputParticleMeasurementsMap{
      this, "OutputParticleMeasurementsMap"};
};

}  // namespace ActsExamples
