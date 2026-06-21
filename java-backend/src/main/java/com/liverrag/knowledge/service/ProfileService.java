package com.liverrag.knowledge.service;

import com.liverrag.knowledge.model.UserProfile;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class ProfileService {
    private final Map<Long, UserProfile> profiles = new ConcurrentHashMap<>();

    public UserProfile getOrCreateProfile(Long userId) {
        if (userId == null) {
            return new UserProfile();
        }
        return profiles.computeIfAbsent(userId, id -> {
            UserProfile profile = new UserProfile();
            profile.setUserId(id);
            return profile;
        });
    }

    public UserProfile updateFromInteraction(Long userId, String sessionId, String query, String procedure, String scene) {
        UserProfile profile = getOrCreateProfile(userId);
        if (procedure != null && !procedure.isBlank()) {
            prependUnique(profile.getPreferredProcedures(), procedure);
        }
        String topic = inferTopic(query);
        prependUnique(profile.getPreferredTopics(), topic);
        String sourceType = inferSourceType(query);
        if (sourceType != null) {
            prependUnique(profile.getPreferredSourceTypes(), sourceType);
        }
        String modality = inferModality(query);
        if (modality != null) {
            prependUnique(profile.getPreferredModalities(), modality);
        }
        if (profile.getLevel() == null) {
            profile.setLevel(inferLevel(query));
        }
        if (profile.getLearningGoal() == null) {
            profile.setLearningGoal(scene == null || scene.isBlank() ? "learning" : scene);
        }
        Map<String, Object> interaction = new LinkedHashMap<>();
        interaction.put("sessionId", sessionId);
        interaction.put("query", query);
        interaction.put("procedure", procedure);
        interaction.put("topic", topic);
        profile.getRecentInteractions().add(0, interaction);
        if (profile.getRecentInteractions().size() > 10) {
            profile.setRecentInteractions(new ArrayList<>(profile.getRecentInteractions().subList(0, 10)));
        }
        return profile;
    }

    public UserProfile applyFeedback(UserProfile profile, String feedbackType, String materialTopic, String materialModality, String materialSourceType) {
        Map<String, Object> signals = profile.getFeedbackSignals();
        Map<String, Integer> counts = (Map<String, Integer>) signals.getOrDefault("counts", new HashMap<String, Integer>());
        counts.put(feedbackType, counts.getOrDefault(feedbackType, 0) + 1);
        signals.put("counts", counts);
        if (materialTopic != null) {
            prependUnique(profile.getPreferredTopics(), materialTopic);
        }
        if (materialModality != null) {
            prependUnique(profile.getPreferredModalities(), materialModality);
        }
        if (materialSourceType != null) {
            prependUnique(profile.getPreferredSourceTypes(), materialSourceType);
        }
        return profile;
    }

    private static void prependUnique(List<String> items, String value) {
        if (value == null || value.isBlank()) {
            return;
        }
        items.remove(value);
        items.add(0, value);
    }

    private static String inferTopic(String query) {
        String q = query.toLowerCase();
        if (q.contains("risk") || q.contains("injury") || q.contains("并发症")) return "risk_points";
        if (q.contains("step") || q.contains("technique") || q.contains("步骤")) return "operative_steps";
        if (q.contains("anatomy") || q.contains("解剖")) return "anatomy";
        return "disease_background";
    }

    private static String inferSourceType(String query) {
        String q = query.toLowerCase();
        if (q.contains("guideline") || q.contains("指南")) return "guideline";
        if (q.contains("case") || q.contains("病例")) return "case";
        if (q.contains("review") || q.contains("综述")) return "review";
        return null;
    }

    private static String inferModality(String query) {
        String q = query.toLowerCase();
        if (q.contains("video") || q.contains("视频")) return "video";
        if (q.contains("image") || q.contains("图")) return "image";
        return "text";
    }

    private static String inferLevel(String query) {
        String q = query.toLowerCase();
        if (q.contains("advanced") || q.contains("进阶")) return "advanced";
        return "beginner";
    }
}
