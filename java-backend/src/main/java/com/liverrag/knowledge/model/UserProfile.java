package com.liverrag.knowledge.model;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class UserProfile {
    private Long userId;
    private String role;
    private String level;
    private List<String> preferredProcedures = new ArrayList<>();
    private List<String> preferredTopics = new ArrayList<>();
    private List<String> preferredModalities = new ArrayList<>();
    private List<String> preferredSourceTypes = new ArrayList<>();
    private String learningGoal;
    private List<Map<String, Object>> recentInteractions = new ArrayList<>();
    private Map<String, Object> feedbackSignals = new HashMap<>();

    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }
    public String getRole() { return role; }
    public void setRole(String role) { this.role = role; }
    public String getLevel() { return level; }
    public void setLevel(String level) { this.level = level; }
    public List<String> getPreferredProcedures() { return preferredProcedures; }
    public void setPreferredProcedures(List<String> preferredProcedures) { this.preferredProcedures = preferredProcedures; }
    public List<String> getPreferredTopics() { return preferredTopics; }
    public void setPreferredTopics(List<String> preferredTopics) { this.preferredTopics = preferredTopics; }
    public List<String> getPreferredModalities() { return preferredModalities; }
    public void setPreferredModalities(List<String> preferredModalities) { this.preferredModalities = preferredModalities; }
    public List<String> getPreferredSourceTypes() { return preferredSourceTypes; }
    public void setPreferredSourceTypes(List<String> preferredSourceTypes) { this.preferredSourceTypes = preferredSourceTypes; }
    public String getLearningGoal() { return learningGoal; }
    public void setLearningGoal(String learningGoal) { this.learningGoal = learningGoal; }
    public List<Map<String, Object>> getRecentInteractions() { return recentInteractions; }
    public void setRecentInteractions(List<Map<String, Object>> recentInteractions) { this.recentInteractions = recentInteractions; }
    public Map<String, Object> getFeedbackSignals() { return feedbackSignals; }
    public void setFeedbackSignals(Map<String, Object> feedbackSignals) { this.feedbackSignals = feedbackSignals; }
}
