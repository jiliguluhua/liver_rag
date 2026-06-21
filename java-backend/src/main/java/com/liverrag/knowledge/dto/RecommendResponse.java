package com.liverrag.knowledge.dto;

import com.liverrag.knowledge.model.RecommendationItem;
import com.liverrag.knowledge.model.UserProfile;

import java.util.List;
import java.util.Map;

public record RecommendResponse(
        String sessionId,
        String procedure,
        String scene,
        Long recommendationLogId,
        UserProfile userProfile,
        List<RecommendationItem> recommendedMaterials,
        Map<String, List<String>> topicGrouping,
        String recommendReason,
        String nextStep
) {}
