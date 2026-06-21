package com.liverrag.knowledge.dto;

import com.liverrag.knowledge.model.UserProfile;

public record RecommendationFeedbackResponse(
        String status,
        String sessionId,
        UserProfile userProfile
) {}
