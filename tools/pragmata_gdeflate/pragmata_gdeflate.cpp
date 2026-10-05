#include <cstddef>
#include <cstdint>

#include "GDeflate.h"

#if defined(_WIN32)
#define PRAGMATA_GDEFLATE_EXPORT extern "C" __declspec(dllexport)
#else
#define PRAGMATA_GDEFLATE_EXPORT extern "C" __attribute__((visibility("default")))
#endif

PRAGMATA_GDEFLATE_EXPORT std::uint32_t pragmata_gdeflate_abi_version()
{
    return 1;
}

PRAGMATA_GDEFLATE_EXPORT int pragmata_gdeflate_decompress(
    std::uint8_t* output,
    std::size_t outputSize,
    const std::uint8_t* input,
    std::size_t inputSize)
{
    try
    {
        return GDeflate::Decompress(output, outputSize, input, inputSize, 1) ? 1 : 0;
    }
    catch (...)
    {
        return 0;
    }
}
