#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <ViGEm/Client.h>
#include <cstring>

static PVIGEM_CLIENT g_client = nullptr;
static PVIGEM_TARGET g_pad    = nullptr;
static bool          g_added  = false;
static XUSB_REPORT   g_report{};

extern "C" {

__declspec(dllexport) int pad_init() {
    if (g_added) return 0;
    g_client = vigem_alloc();
    if (!g_client) return -1;
    if (!VIGEM_SUCCESS(vigem_connect(g_client))) {
        vigem_free(g_client);
        g_client = nullptr;
        return -2;
    }
    g_pad = vigem_target_x360_alloc();
    if (!g_pad || !VIGEM_SUCCESS(vigem_target_add(g_client, g_pad))) {
        if (g_pad) { vigem_target_free(g_pad); g_pad = nullptr; }
        vigem_disconnect(g_client);
        vigem_free(g_client);
        g_client = nullptr;
        return -3;
    }
    g_added = true;
    std::memset(&g_report, 0, sizeof(g_report));
    vigem_target_x360_update(g_client, g_pad, g_report);
    return 0;
}

__declspec(dllexport) void pad_shutdown() {
    if (g_pad) {
        if (g_added) {
            std::memset(&g_report, 0, sizeof(g_report));
            vigem_target_x360_update(g_client, g_pad, g_report);
            vigem_target_remove(g_client, g_pad);
        }
        vigem_target_free(g_pad);
        g_pad = nullptr;
        g_added = false;
    }
    if (g_client) {
        vigem_disconnect(g_client);
        vigem_free(g_client);
        g_client = nullptr;
    }
}

__declspec(dllexport) int pad_set(unsigned short buttons, short lx, short ly, short rx, short ry, unsigned char lt, unsigned char rt) {
    if (!g_added) return -1;
    g_report.wButtons      = buttons;
    g_report.sThumbLX      = lx;
    g_report.sThumbLY      = ly;
    g_report.sThumbRX      = rx;
    g_report.sThumbRY      = ry;
    g_report.bLeftTrigger  = lt;
    g_report.bRightTrigger = rt;
    return VIGEM_SUCCESS(vigem_target_x360_update(g_client, g_pad, g_report)) ? 0 : -2;
}

__declspec(dllexport) int pad_press(unsigned short buttons, int hold_ms) {
    if (!g_added) return -1;
    g_report.wButtons |= buttons;
    vigem_target_x360_update(g_client, g_pad, g_report);
    Sleep(hold_ms > 0 ? hold_ms : 100);
    g_report.wButtons &= ~buttons;
    return VIGEM_SUCCESS(vigem_target_x360_update(g_client, g_pad, g_report)) ? 0 : -2;
}

} // extern "C"

