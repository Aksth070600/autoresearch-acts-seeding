// Minimal project-owned SHA-256 implementation for canonical semantic hashes.
#pragma once

#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <span>
#include <string>

namespace ActsExamples::OwnedSeedingDetail {

class Sha256 {
 public:
  void update(std::span<const std::byte> input) {
    for (std::byte byte : input) {
      m_block[m_blockSize++] = std::to_integer<std::uint8_t>(byte);
      m_bitSize += 8;
      if (m_blockSize == 64) {
        transform();
        m_blockSize = 0;
      }
    }
  }

  std::array<std::uint8_t, 32> finalize() {
    const std::uint64_t messageBitSize = m_bitSize;
    m_block[m_blockSize++] = 0x80;
    if (m_blockSize > 56) {
      while (m_blockSize < 64) {
        m_block[m_blockSize++] = 0;
      }
      transform();
      m_blockSize = 0;
    }
    while (m_blockSize < 56) {
      m_block[m_blockSize++] = 0;
    }
    for (int shift = 56; shift >= 0; shift -= 8) {
      m_block[m_blockSize++] =
          static_cast<std::uint8_t>((messageBitSize >> shift) & 0xffu);
    }
    transform();

    std::array<std::uint8_t, 32> digest{};
    for (std::size_t i = 0; i < m_state.size(); ++i) {
      digest[4 * i] = static_cast<std::uint8_t>(m_state[i] >> 24);
      digest[4 * i + 1] = static_cast<std::uint8_t>(m_state[i] >> 16);
      digest[4 * i + 2] = static_cast<std::uint8_t>(m_state[i] >> 8);
      digest[4 * i + 3] = static_cast<std::uint8_t>(m_state[i]);
    }
    return digest;
  }

 private:
  static constexpr std::array<std::uint32_t, 64> kRound = {
      0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u,
      0x3956c25bu, 0x59f111f1u, 0x923f82a4u, 0xab1c5ed5u,
      0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u,
      0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u,
      0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu,
      0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
      0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u,
      0xc6e00bf3u, 0xd5a79147u, 0x06ca6351u, 0x14292967u,
      0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u,
      0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u,
      0xa2bfe8a1u, 0xa81a664bu, 0xc24b8b70u, 0xc76c51a3u,
      0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
      0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u,
      0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu, 0x682e6ff3u,
      0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
      0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u};

  void transform() {
    std::array<std::uint32_t, 64> words{};
    for (std::size_t i = 0; i < 16; ++i) {
      words[i] = (static_cast<std::uint32_t>(m_block[4 * i]) << 24) |
                 (static_cast<std::uint32_t>(m_block[4 * i + 1]) << 16) |
                 (static_cast<std::uint32_t>(m_block[4 * i + 2]) << 8) |
                 static_cast<std::uint32_t>(m_block[4 * i + 3]);
    }
    for (std::size_t i = 16; i < words.size(); ++i) {
      const std::uint32_t s0 = std::rotr(words[i - 15], 7) ^
                               std::rotr(words[i - 15], 18) ^
                               (words[i - 15] >> 3);
      const std::uint32_t s1 = std::rotr(words[i - 2], 17) ^
                               std::rotr(words[i - 2], 19) ^
                               (words[i - 2] >> 10);
      words[i] = words[i - 16] + s0 + words[i - 7] + s1;
    }

    auto [a, b, c, d, e, f, g, h] = m_state;
    for (std::size_t i = 0; i < words.size(); ++i) {
      const std::uint32_t sum1 = std::rotr(e, 6) ^ std::rotr(e, 11) ^
                                 std::rotr(e, 25);
      const std::uint32_t choose = (e & f) ^ (~e & g);
      const std::uint32_t temp1 = h + sum1 + choose + kRound[i] + words[i];
      const std::uint32_t sum0 = std::rotr(a, 2) ^ std::rotr(a, 13) ^
                                 std::rotr(a, 22);
      const std::uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
      const std::uint32_t temp2 = sum0 + majority;
      h = g;
      g = f;
      f = e;
      e = d + temp1;
      d = c;
      c = b;
      b = a;
      a = temp1 + temp2;
    }
    m_state[0] += a;
    m_state[1] += b;
    m_state[2] += c;
    m_state[3] += d;
    m_state[4] += e;
    m_state[5] += f;
    m_state[6] += g;
    m_state[7] += h;
  }

  std::array<std::uint32_t, 8> m_state = {
      0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
      0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u};
  std::array<std::uint8_t, 64> m_block{};
  std::size_t m_blockSize = 0;
  std::uint64_t m_bitSize = 0;
};

inline std::string hexDigest(const std::array<std::uint8_t, 32>& digest) {
  static constexpr char kHex[] = "0123456789abcdef";
  std::string result(64, '0');
  for (std::size_t i = 0; i < digest.size(); ++i) {
    result[2 * i] = kHex[digest[i] >> 4];
    result[2 * i + 1] = kHex[digest[i] & 0x0f];
  }
  return result;
}

}  // namespace ActsExamples::OwnedSeedingDetail
