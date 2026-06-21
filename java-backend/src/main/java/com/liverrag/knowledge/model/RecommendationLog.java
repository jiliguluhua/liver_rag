package com.liverrag.knowledge.model;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

public class RecommendationLog {
    private Long id;
    private String sessionId;
    private Long userId;
    private String query;
    private String procedure;
    private String topic;
    private UserProfile profileSnapshot;
    private List<RecommendationItem> recommendations = new ArrayList<>();
    private Instant createdAt = Instant.now();

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getSessionId() { return sessionId; }
    public void setSessionId(String sessionId) { this.sessionId = sessionId; }
    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }
    public String getQuery() { return query; }
    public void setQuery(String query) { this.query = query; }
    public String getProcedure() { return procedure; }
    public void setProcedure(String procedure) { this.procedure = procedure; }
    public String getTopic() { return topic; }
    public void setTopic(String topic) { this.topic = topic; }
    public UserProfile getProfileSnapshot() { return profileSnapshot; }
    public void setProfileSnapshot(UserProfile profileSnapshot) { this.profileSnapshot = profileSnapshot; }
    public List<RecommendationItem> getRecommendations() { return recommendations; }
    public void setRecommendations(List<RecommendationItem> recommendations) { this.recommendations = recommendations; }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
}
