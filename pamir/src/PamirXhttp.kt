package com.v2ray.ang.pamir

import com.google.gson.JsonObject

/**
 * xhttp settings the panel cannot pass in the subscription.
 *
 * LTE servers go through a CDN that only lets GET through, so the phone puts its upload into request headers
 * (uplinkDataPlacement = header/cookie). Xray's default is up to 1 MB per request (~1.3 MB of headers), which
 * the CDN rejects: big uploads (sign-ins, photos, forms) broke and pages hung. 32 KB per request passes
 * (measured through the CDN: 1 MB upload OK at ~4 Mbit/s, pages open the same). The panel (3x-ui 3.8.5) does not
 * put scMaxEachPostBytes into the link's "extra", so the app sets it; a value from the subscription wins.
 * Remove when the panel passes scMaxEachPostBytes in "extra".
 */
object PamirXhttp {
    private const val HEADER_UPLOAD_BYTES = 32000

    fun tune(extra: JsonObject?): JsonObject? {
        if (extra == null) return null
        val placement = extra.get("uplinkDataPlacement")?.takeIf { it.isJsonPrimitive }?.asString
        if ((placement == "header" || placement == "cookie") && !extra.has("scMaxEachPostBytes")) {
            extra.addProperty("scMaxEachPostBytes", HEADER_UPLOAD_BYTES)
        }
        return extra
    }
}
