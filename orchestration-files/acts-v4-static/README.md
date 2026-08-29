# Owned static ACTS Seeding v4 qualification

This module implements the qualification-only owned static input path for ACTS
v46.5.0 at commit `34edd48852f766e1b9d94d3dc996e27476339f1b`.
It does not define a production protocol, canonical dataset, Genesis pool,
record type, storage location, publication actor, or compression choice.
Generated data and results must stay outside the repository.

## Boundary and data contract

`OwnedSeedingDatasetWriter` runs after digitization, digitized-particle
selection, and pixel `SpacePointMaker`. One ROOT tree entry contains the exact
ordered measurements, pixel space points and source links, all simulated
particles, selected markers, and both truth maps. The manifest contains strict
identity, count, and per-section semantic hashes. `SHA256SUMS` binds the
manifest and ROOT transport bytes.

`OwnedSeedingDatasetReader` validates the complete event before the first
WhiteBoard publication. It rejects branch drift, malformed arrays, non-finite
or non-unit values, unresolved geometry/source/truth identities, truth-map
inversion differences, and semantic hash differences. Static process output is
staged and removed on failure.

ACTS normalizes `Particle::setDirection`, which can change an already-normalized
vector by one bit. The content-addressed v46.5.0 patch grants friendship only to
`OwnedSeedingParticleDirectionRestorer`. The reader uses this private access
after full event validation, then proves every restored component with a raw
bit comparison. It does not add a public unchecked particle setter.

## Private build

Use a new private ACTS root. Never point these commands at the shared ACTS
source or build.

```sh
ACTS_SOURCE=/private/acts/source \
ACTS_BUILD_DIR=/private/acts/build \
ACTS_BUILD_JOBS=8 \
bash orchestration-files/HEPP-files/acts-v4-static-private-build.sh \
  /trusted/acts-v46.5.0 \
  "$PWD/orchestration-files/acts-v4-static"
```

On HEPP02, invoke helpers only through `HEPP-files/run-hepp-helper.sh` and the
persistent pinned AlmaLinux container. The helpers source LCG inside the
container. `apply_overlay.py`, `invalidate_build.py`, and
`write_build_identity.py` bind the upstream commit, patch, modified/added
files, exact invalidated objects, and built artifacts.

## Generation and qualification

`build_dataset.py` writes only a generation staging directory.
`finalize_dataset.py` requires a successful complete process, writes the strict
three-file dataset in a hidden directory, validates it, and atomically renames
it. Failed final validation restores the payload to generation staging and
removes the hidden publication directory.

`acts-v4-static-roundtrip.sh` runs generation and static reading in separate
Python processes, then `compare_generated_static.py` requires equal input
hashes, ordered downstream diagnostics, match classifications, and all eight
`TrackFinderPerformanceCollector::Stats` integers.

`acts-v4-static-negative-qualification.sh` makes disposable copies and proves
rejection of transport and manifest tampering, protocol drift, malformed CSR,
non-finite data, unresolved geometry/source/truth identities, and map inversion
without partial result publication. Unit tests cover missing, duplicate, and
reordered events, old protocols, incomplete/FPE runs, covariance and relation
shape errors, result precision, and failed publication rollback.

`acts-v4-static-timed.sh` wraps exactly one static Python process with GNU
`/usr/bin/time -v`. `parse_result.py` emits exact rate numerator/denominator
pairs and rejects incomplete events, unexpected FPEs, identity drift, process
wall above 180 seconds, and a supplied total latency above 300 seconds.

Run repository checks with:

```sh
make test
```

## Non-evidence qualification result

The isolated HEPP02 qualification used ITk, seed 42, pileup 200, one thread, 50
ordered events, and at most eight build jobs. One-event and 50-event
cross-process equality passed. All three provisional transports produced the
same equality proof SHA-256
`62c6f676306459ad571d3e8dd11d953018b8e667217ea23255d18dcab9206dc7`
and the same exact aggregate counts:

- selected/matched particles: `58310` / `57398`;
- converted/matched/fake/duplicate tracks: `1065071` / `644305` / `26451` /
  `586907`;
- ordered downstream diagnostics SHA-256:
  `7eeba9d323ae8878e51e9caef710c9e3d57bcf177e0914a646a72ab269fa113a`.

| Provisional transport | Payload bytes | Process wall | Peak RSS KB | GridTriplet total |
| --- | ---: | ---: | ---: | ---: |
| uncompressed, level 0 | 1,362,570,883 | 77.48 s | 2,127,136 | 14.8112 s |
| LZ4, level 4 | 519,161,017 | 77.07 s | 2,124,428 | 14.8281 s |
| ZSTD, level 5 | 335,989,011 | 77.48 s | 2,122,376 | 14.7515 s |

These single observations are a bounded format comparison, not a compression
selection or latency distribution. Every process passed the 180-second target
with zero unmasked FPEs. The final high-fanout incremental build took 131.502
seconds, followed by 35.681 seconds for explicit invalidation, rebuild,
identity, and import checks. It therefore failed the separate 45-second
preparation/build target. Adding the 80.804-second LZ4 timed helper boundary
gives a 247.987-second measured lower bound, but it excludes queueing, source
transport/reset, and publication. It is not proof of the 300-second
queue-to-record target.

No Development/Evaluation record or canonical dataset was created. Production
still requires captain decisions and a separate authorized publication step.
