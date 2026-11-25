#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <cstdint>
#include <cstring>
#include <string>
#include <unordered_map>
#include <vector>

struct MonitorDup {
    ID3D11Device* device = nullptr;
    ID3D11DeviceContext* ctx = nullptr;
    IDXGIOutputDuplication* dup = nullptr;
    ID3D11Texture2D* staging = nullptr;
    RECT bounds = {0, 0, 0, 0};
    int width = 0;
    int height = 0;
    std::vector<uint8_t> cached_bgra;
    bool has_cache = false;
    int timeout_streak = 0;

    void release() {
        if (staging) { staging->Release(); staging = nullptr; }
        if (dup) { dup->Release(); dup = nullptr; }
        if (ctx) { ctx->Release(); ctx = nullptr; }
        if (device) { device->Release(); device = nullptr; }
        cached_bgra.clear();
        has_cache = false;
        timeout_streak = 0;
        width = 0;
        height = 0;
    }

    ~MonitorDup() {
        release();
    }
};

static CRITICAL_SECTION g_cs;
static bool g_cs_init = false;
static std::unordered_map<std::wstring, MonitorDup> g_dups;

struct CsLock {
    CsLock() {
        if (!g_cs_init) {
            InitializeCriticalSection(&g_cs);
            g_cs_init = true;
        }
        EnterCriticalSection(&g_cs);
    }
    ~CsLock() { LeaveCriticalSection(&g_cs); }
};

static bool init_duplicator(const wchar_t* target_dev, MonitorDup& out) {
    out.release();

    IDXGIFactory1* factory = nullptr;
    if (FAILED(CreateDXGIFactory1(__uuidof(IDXGIFactory1), reinterpret_cast<void**>(&factory))) || !factory) {
        return false;
    }

    IDXGIAdapter1* adapter = nullptr;
    bool found = false;

    for (UINT ai = 0; factory->EnumAdapters1(ai, &adapter) != DXGI_ERROR_NOT_FOUND; ++ai) {
        IDXGIOutput* output = nullptr;
        for (UINT oi = 0; adapter->EnumOutputs(oi, &output) != DXGI_ERROR_NOT_FOUND; ++oi) {
            DXGI_OUTPUT_DESC desc = {};
            if (SUCCEEDED(output->GetDesc(&desc))) {
                if (_wcsicmp(desc.DeviceName, target_dev) == 0) {
                    D3D_FEATURE_LEVEL fl = D3D_FEATURE_LEVEL_11_0;
                    HRESULT hr = D3D11CreateDevice(
                        adapter,
                        D3D_DRIVER_TYPE_UNKNOWN,
                        nullptr,
                        0,
                        nullptr,
                        0,
                        D3D11_SDK_VERSION,
                        &out.device,
                        &fl,
                        &out.ctx
                    );
                    if (SUCCEEDED(hr) && out.device && out.ctx) {
                        IDXGIOutput1* out1 = nullptr;
                        if (SUCCEEDED(output->QueryInterface(__uuidof(IDXGIOutput1), reinterpret_cast<void**>(&out1))) && out1) {
                            hr = out1->DuplicateOutput(out.device, &out.dup);
                            out1->Release();
                            if (SUCCEEDED(hr) && out.dup) {
                                out.bounds = desc.DesktopCoordinates;
                                out.width = static_cast<int>(out.bounds.right - out.bounds.left);
                                out.height = static_cast<int>(out.bounds.bottom - out.bounds.top);
                                if (out.width > 0 && out.height > 0) {
                                    D3D11_TEXTURE2D_DESC td = {};
                                    td.Width = static_cast<UINT>(out.width);
                                    td.Height = static_cast<UINT>(out.height);
                                    td.MipLevels = 1;
                                    td.ArraySize = 1;
                                    td.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
                                    td.SampleDesc.Count = 1;
                                    td.Usage = D3D11_USAGE_STAGING;
                                    td.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
                                    if (SUCCEEDED(out.device->CreateTexture2D(&td, nullptr, &out.staging)) && out.staging) {
                                        out.cached_bgra.resize(static_cast<size_t>(out.width) * out.height * 4);
                                        found = true;
                                    }
                                }
                            }
                        }
                    }
                    output->Release();
                    break;
                }
            }
            output->Release();
        }
        adapter->Release();
        if (found) break;
    }

    factory->Release();
    if (!found) {
        out.release();
    }
    return found;
}

static bool acquire_monitor_frame(const wchar_t* dev_name, MonitorDup& m) {
    if (!m.dup) {
        if (!init_duplicator(dev_name, m)) {
            return false;
        }
    }

    for (int attempt = 0; attempt < 2; ++attempt) {
        IDXGIResource* res = nullptr;
        DXGI_OUTDUPL_FRAME_INFO info = {};
        UINT timeout = m.has_cache ? 80 : 250;
        HRESULT hr = m.dup->AcquireNextFrame(timeout, &info, &res);

        if (hr == DXGI_ERROR_WAIT_TIMEOUT) {
            m.timeout_streak++;
            if (m.has_cache && m.timeout_streak <= 2) {
                return true;
            }
            m.release();
            return false;
        }
        if (hr == DXGI_ERROR_ACCESS_LOST) {
            if (res) res->Release();
            if (!init_duplicator(dev_name, m)) {
                return false;
            }
            continue;
        }
        if (FAILED(hr) || !res) {
            if (res) res->Release();
            m.release();
            return false;
        }
        m.timeout_streak = 0;

        ID3D11Texture2D* tex = nullptr;
        bool copied = false;
        if (SUCCEEDED(res->QueryInterface(__uuidof(ID3D11Texture2D), reinterpret_cast<void**>(&tex))) && tex) {
            m.ctx->CopyResource(m.staging, tex);
            tex->Release();

            D3D11_MAPPED_SUBRESOURCE mapped = {};
            if (SUCCEEDED(m.ctx->Map(m.staging, 0, D3D11_MAP_READ, 0, &mapped))) {
                const uint8_t* src = reinterpret_cast<const uint8_t*>(mapped.pData);
                size_t row_bytes = static_cast<size_t>(m.width) * 4;
                for (int y = 0; y < m.height; ++y) {
                    std::memcpy(
                        m.cached_bgra.data() + static_cast<size_t>(y) * row_bytes,
                        src + static_cast<size_t>(y) * mapped.RowPitch,
                        row_bytes
                    );
                }
                m.ctx->Unmap(m.staging, 0);
                m.has_cache = true;
                copied = true;
            }
        }
        res->Release();
        m.dup->ReleaseFrame();
        return copied || m.has_cache;
    }

    return m.has_cache;
}

extern "C" {

__declspec(dllexport) int dxgi_grab_rect(
    const wchar_t* device_name,
    int x,
    int y,
    int w,
    int h,
    uint8_t* out_bgra,
    int out_capacity_bytes
) {
    if (!device_name || !out_bgra || w <= 0 || h <= 0) {
        return -1;
    }
    const size_t needed = static_cast<size_t>(w) * static_cast<size_t>(h) * 4;
    if (static_cast<size_t>(out_capacity_bytes) < needed) {
        return -2;
    }

    CsLock lk;
    std::wstring key(device_name);
    MonitorDup& m = g_dups[key];

    if (!acquire_monitor_frame(device_name, m)) {
        return 0;
    }

    // Clamp crop rect within the monitor's bounds
    int rel_x = x - static_cast<int>(m.bounds.left);
    int rel_y = y - static_cast<int>(m.bounds.top);
    if (rel_x < 0) rel_x = 0;
    if (rel_y < 0) rel_y = 0;
    if (rel_x + w > m.width || rel_y + h > m.height) {
        return -3;
    }

    const size_t mon_stride = static_cast<size_t>(m.width) * 4;
    const size_t copy_stride = static_cast<size_t>(w) * 4;
    for (int row = 0; row < h; ++row) {
        const uint8_t* src_row = m.cached_bgra.data() + static_cast<size_t>(rel_y + row) * mon_stride + static_cast<size_t>(rel_x) * 4;
        std::memcpy(out_bgra + static_cast<size_t>(row) * copy_stride, src_row, copy_stride);
    }

    return 1;
}

__declspec(dllexport) void dxgi_shutdown() {
    CsLock lk;
    g_dups.clear();
}

}
