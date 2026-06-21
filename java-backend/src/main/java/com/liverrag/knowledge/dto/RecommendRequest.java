package com.liverrag.knowledge.dto;

import jakarta.validation.constraints.NotBlank;

public record RecommendRequest(
        @NotBlank String query,
        String sessionId,
        Long userId,
        String procedure,
        String scene,
        String sessionSummary
) {}
