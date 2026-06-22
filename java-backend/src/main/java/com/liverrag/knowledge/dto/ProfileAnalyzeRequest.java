package com.liverrag.knowledge.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record ProfileAnalyzeRequest(
        @JsonProperty("session_id") @NotBlank String sessionId,
        @JsonProperty("user_id") Long userId,
        @JsonProperty("max_turns") @Min(1) @Max(50) Integer maxTurns
) {}
