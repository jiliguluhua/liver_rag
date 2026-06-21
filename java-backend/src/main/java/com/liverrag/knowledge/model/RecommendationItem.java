package com.liverrag.knowledge.model;

import java.util.HashMap;
import java.util.Map;

public class RecommendationItem {
    private String title;
    private String procedure;
    private String topic;
    private String sourceType;
    private String modality;
    private String source;
    private String sourceUrl;
    private String reason;
    private String relevanceToQuery;
    private String suitableForLevel;
    private double score;
    private Map<String, Object> explanation = new HashMap<>();

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getProcedure() { return procedure; }
    public void setProcedure(String procedure) { this.procedure = procedure; }
    public String getTopic() { return topic; }
    public void setTopic(String topic) { this.topic = topic; }
    public String getSourceType() { return sourceType; }
    public void setSourceType(String sourceType) { this.sourceType = sourceType; }
    public String getModality() { return modality; }
    public void setModality(String modality) { this.modality = modality; }
    public String getSource() { return source; }
    public void setSource(String source) { this.source = source; }
    public String getSourceUrl() { return sourceUrl; }
    public void setSourceUrl(String sourceUrl) { this.sourceUrl = sourceUrl; }
    public String getReason() { return reason; }
    public void setReason(String reason) { this.reason = reason; }
    public String getRelevanceToQuery() { return relevanceToQuery; }
    public void setRelevanceToQuery(String relevanceToQuery) { this.relevanceToQuery = relevanceToQuery; }
    public String getSuitableForLevel() { return suitableForLevel; }
    public void setSuitableForLevel(String suitableForLevel) { this.suitableForLevel = suitableForLevel; }
    public double getScore() { return score; }
    public void setScore(double score) { this.score = score; }
    public Map<String, Object> getExplanation() { return explanation; }
    public void setExplanation(Map<String, Object> explanation) { this.explanation = explanation; }
}
