package com.liverrag.knowledge.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

public record ProfileAnalyzeResponse(
        @JsonProperty("session_id") String sessionId,
        @JsonProperty("inferred_user_label") String inferredUserLabel,
        String role,
        String level,
        @JsonProperty("preferred_procedures") List<String> preferredProcedures,
        @JsonProperty("preferred_topics") List<String> preferredTopics,
        @JsonProperty("preferred_modalities") List<String> preferredModalities,
        @JsonProperty("learning_goal") String learningGoal,
        @JsonProperty("recent_focus") List<String> recentFocus,
        @JsonProperty("evidence_queries") List<String> evidenceQueries,
        @JsonProperty("profile_summary") String profileSummary
) {}
