package com.liverrag.knowledge.dto;

import jakarta.validation.constraints.NotBlank;

public record RecommendationFeedbackRequest(
        @NotBlank String sessionId,
        Long userId,
        Long recommendationLogId,
        @NotBlank String materialTitle,
        @NotBlank String feedbackType,
        boolean value,
        String reason
) {}
