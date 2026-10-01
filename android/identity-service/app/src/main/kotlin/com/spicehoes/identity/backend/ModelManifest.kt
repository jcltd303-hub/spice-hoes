package com.spicehoes.identity.backend

data class ModelManifest(
    val id: String,
    val fileName: String,
    val sha256: String?,
    val source: String,
    val codeLicense: String,
    val weightsLicense: String,
    val commercialUse: Boolean,
    val inputSize: Int,
    val runtimeFormat: String,
)

object ProductionModels {
    /**
     * Candidate only until the exact bundled artifact checksum and upstream license
     * are verified during packaging. Never silently download or claim readiness.
     */
    val GHOST_1_256 = ModelManifest(
        id = "ghost_1_256",
        fileName = "ghost_1_256.onnx",
        sha256 = null,
        source = "ai-forever Ghost / FaceFusion model registry",
        codeLicense = "Apache-2.0",
        weightsLicense = "Apache-2.0-candidate-requires-artifact-verification",
        commercialUse = false,
        inputSize = 256,
        runtimeFormat = "onnx",
    )
}
