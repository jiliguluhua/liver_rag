package com.liverrag.knowledge.model;

import java.time.Instant;

public class RecommendationFeedback {
    private Long recommendationLogId;
    private String sessionId;
    private Long userId;
    private String materialTitle;
    private String feedbackType;
    private boolean value;
    private String reason;
    private Instant createdAt = Instant.now();

    public Long getRecommendationLogId() { return recommendationLogId; }
    public void setRecommendationLogId(Long recommendationLogId) { this.recommendationLogId = recommendationLogId; }
    public String getSessionId() { return sessionId; }
    public void setSessionId(String sessionId) { this.sessionId = sessionId; }
    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }
    public String getMaterialTitle() { return materialTitle; }
    public void setMaterialTitle(String materialTitle) { this.materialTitle = materialTitle; }
    public String getFeedbackType() { return feedbackType; }
    public void setFeedbackType(String feedbackType) { this.feedbackType = feedbackType; }
    public boolean isValue() { return value; }
    public void setValue(boolean value) { this.value = value; }
    public String getReason() { return reason; }
    public void setReason(String reason) { this.reason = reason; }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
}
