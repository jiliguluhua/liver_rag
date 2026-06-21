package com.liverrag.knowledge.service;

import com.liverrag.knowledge.dto.RecommendRequest;
import com.liverrag.knowledge.dto.RecommendResponse;
import com.liverrag.knowledge.dto.RecommendationFeedbackRequest;
import com.liverrag.knowledge.dto.RecommendationFeedbackResponse;
import com.liverrag.knowledge.model.RecommendationFeedback;
import com.liverrag.knowledge.model.RecommendationItem;
import com.liverrag.knowledge.model.RecommendationLog;
import com.liverrag.knowledge.model.UserProfile;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

@Service
public class RecommendationService {
    private final ProfileService profileService;
    private final AtomicLong logSequence = new AtomicLong(1);
    private final Map<Long, RecommendationLog> logs = new ConcurrentHashMap<>();
    private final List<RecommendationFeedback> feedbackLogs = new ArrayList<>();

    public RecommendationService(ProfileService profileService) {
        this.profileService = profileService;
    }

    public RecommendResponse recommend(RecommendRequest request) {
        String procedure = inferProcedure(request.procedure(), request.query());
        String scene = blankToDefault(request.scene(), "learning");
        String sessionId = blankToDefault(request.sessionId(), "java-session");
        UserProfile profile = profileService.updateFromInteraction(request.userId(), sessionId, request.query(), procedure, scene);

        List<RecommendationItem> items = new ArrayList<>();
        items.add(buildItem("Guideline overview for " + procedure, procedure, "operative_steps", "guideline", "text", request.query(), profile, 9.2));
        items.add(buildItem("Risk points case review for " + procedure, procedure, "risk_points", "case", "text", request.query(), profile, 8.1));
        items.add(buildItem("Anatomy atlas for " + procedure, procedure, "anatomy", "reference", "image", request.query(), profile, 7.4));
        items.sort(Comparator.comparingDouble(RecommendationItem::getScore).reversed());

        RecommendationLog log = new RecommendationLog();
        log.setId(logSequence.getAndIncrement());
        log.setSessionId(sessionId);
        log.setUserId(request.userId());
        log.setQuery(request.query());
        log.setProcedure(procedure);
        log.setTopic(items.get(0).getTopic());
        log.setProfileSnapshot(profile);
        log.setRecommendations(items);
        log.setCreatedAt(Instant.now());
        logs.put(log.getId(), log);

        Map<String, List<String>> topicGrouping = new LinkedHashMap<>();
        for (RecommendationItem item : items) {
            topicGrouping.computeIfAbsent(item.getTopic(), key -> new ArrayList<>()).add(item.getTitle());
        }

        return new RecommendResponse(
                sessionId,
                procedure,
                scene,
                log.getId(),
                profile,
                items,
                topicGrouping,
                "Java recommendation flow combines query, session signal, profile preference, and explainable ranking.",
                "Send feedback after reading to keep the profile and ranking updated."
        );
    }

    public RecommendationFeedbackResponse recordFeedback(RecommendationFeedbackRequest request) {
        UserProfile profile = profileService.getOrCreateProfile(request.userId());
        RecommendationLog log = request.recommendationLogId() == null ? null : logs.get(request.recommendationLogId());
        RecommendationItem matched = null;
        if (log != null) {
            matched = log.getRecommendations().stream()
                    .filter(item -> item.getTitle().equals(request.materialTitle()))
                    .findFirst()
                    .orElse(null);
        }
        profileService.applyFeedback(
                profile,
                request.feedbackType(),
                matched == null ? null : matched.getTopic(),
                matched == null ? null : matched.getModality(),
                matched == null ? null : matched.getSourceType()
        );

        RecommendationFeedback feedback = new RecommendationFeedback();
        feedback.setRecommendationLogId(request.recommendationLogId());
        feedback.setSessionId(request.sessionId());
        feedback.setUserId(request.userId());
        feedback.setMaterialTitle(request.materialTitle());
        feedback.setFeedbackType(request.feedbackType());
        feedback.setValue(request.value());
        feedback.setReason(request.reason());
        feedbackLogs.add(feedback);

        return new RecommendationFeedbackResponse("ok", request.sessionId(), profile);
    }

    private static RecommendationItem buildItem(String title, String procedure, String topic, String sourceType, String modality, String query, UserProfile profile, double score) {
        RecommendationItem item = new RecommendationItem();
        item.setTitle(title);
        item.setProcedure(procedure);
        item.setTopic(topic);
        item.setSourceType(sourceType);
        item.setModality(modality);
        item.setReason("Recommended because it matches the current procedure, topic, and profile preferences.");
        item.setRelevanceToQuery("Directly related to the user's current learning request: " + query);
        item.setSuitableForLevel(profile.getLevel() == null ? "beginner" : profile.getLevel());
        item.setScore(score);
        Map<String, Object> explanation = new HashMap<>();
        explanation.put("matchedProcedure", procedure);
        explanation.put("matchedTopic", topic);
        explanation.put("profileLevel", item.getSuitableForLevel());
        item.setExplanation(explanation);
        return item;
    }

    private static String inferProcedure(String explicitProcedure, String query) {
        if (explicitProcedure != null && !explicitProcedure.isBlank()) {
            return explicitProcedure;
        }
        String q = query.toLowerCase();
        if (q.contains("cholecystectomy")) return "cholecystectomy";
        return "hepatectomy";
    }

    private static String blankToDefault(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value;
    }
}
