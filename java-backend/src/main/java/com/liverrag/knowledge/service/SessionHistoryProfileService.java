package com.liverrag.knowledge.service;

import com.liverrag.knowledge.dto.ProfileAnalyzeResponse;
import com.liverrag.knowledge.dto.ProfileAnalyzeRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

@Service
public class SessionHistoryProfileService {
    private static final List<String> PROCEDURE_KEYWORDS = List.of(
            "hepatectomy", "liver resection", "segmentectomy", "tace", "ablation", "transplant", "cholecystectomy"
    );
    private static final Map<String, List<String>> TOPIC_KEYWORDS = Map.of(
            "risk_points", List.of("risk", "injury", "complication", "bleeding"),
            "operative_steps", List.of("step", "technique", "approach", "procedure"),
            "anatomy", List.of("anatomy", "segment", "vascular", "portal", "hepatic vein"),
            "indications", List.of("indication", "candidate", "when to use"),
            "postoperative_management", List.of("postoperative", "recovery", "follow-up")
    );
    private static final Map<String, List<String>> MODALITY_KEYWORDS = Map.of(
            "video", List.of("video"),
            "image", List.of("image", "atlas", "ct", "mri", "scan"),
            "text", List.of("guideline", "review", "paper", "article")
    );
    private static final Map<String, List<String>> GOAL_KEYWORDS = Map.of(
            "operative mastery", List.of("step", "technique", "procedure", "operate"),
            "risk reduction", List.of("risk", "injury", "complication", "avoid"),
            "knowledge overview", List.of("overview", "background", "review", "summary")
    );
    private static final Map<String, List<String>> LEVEL_KEYWORDS = Map.of(
            "advanced", List.of("advanced", "complex", "difficult", "bailout", "complication"),
            "beginner", List.of("basic", "overview", "intro", "anatomy", "step by step")
    );

    private final String sqlitePath;

    public SessionHistoryProfileService(@Value("${knowledge.sqlite-path:../data/liver_rag_api.db}") String sqlitePath) {
        this.sqlitePath = sqlitePath;
    }

    public ProfileAnalyzeResponse analyze(ProfileAnalyzeRequest request) {
        int maxTurns = request.maxTurns() == null ? 10 : request.maxTurns();
        List<SessionTurn> turns = loadTurns(request.sessionId(), maxTurns);
        return buildResponse(request.sessionId(), request.userId(), turns);
    }

    private List<SessionTurn> loadTurns(String sessionId, int maxTurns) {
        List<SessionTurn> merged = new ArrayList<>();
        String jdbcUrl = "jdbc:sqlite:" + sqlitePath;
        try (Connection connection = DriverManager.getConnection(jdbcUrl)) {
            loadIntakeTurns(connection, sessionId, merged);
            loadConsultTurns(connection, sessionId, merged);
        } catch (SQLException ex) {
            throw new IllegalStateException("Failed to load session history from SQLite: " + sqlitePath, ex);
        }
        merged.sort(Comparator.comparing(SessionTurn::createdAt, Comparator.nullsLast(Comparator.naturalOrder())));
        if (merged.size() <= maxTurns) {
            return merged;
        }
        return new ArrayList<>(merged.subList(merged.size() - maxTurns, merged.size()));
    }

    private void loadIntakeTurns(Connection connection, String sessionId, List<SessionTurn> merged) throws SQLException {
        String sql = "select query, assistant_message, image_path, created_at from intake_messages where session_id = ? order by created_at asc";
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, sessionId);
            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    merged.add(new SessionTurn(
                            resultSet.getString("query"),
                            resultSet.getString("assistant_message"),
                            resultSet.getString("image_path"),
                            resultSet.getTimestamp("created_at"),
                            "collect"
                    ));
                }
            }
        }
    }

    private void loadConsultTurns(Connection connection, String sessionId, List<SessionTurn> merged) throws SQLException {
        String sql = "select query, report, image_path, created_at from consultations where session_id = ? order by created_at asc";
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, sessionId);
            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    merged.add(new SessionTurn(
                            resultSet.getString("query"),
                            resultSet.getString("report"),
                            resultSet.getString("image_path"),
                            resultSet.getTimestamp("created_at"),
                            "report"
                    ));
                }
            }
        }
    }

    private ProfileAnalyzeResponse buildResponse(String sessionId, Long userId, List<SessionTurn> turns) {
        List<String> queries = turns.stream()
                .map(SessionTurn::query)
                .filter(Objects::nonNull)
                .map(String::trim)
                .filter(value -> !value.isEmpty())
                .toList();

        Counter procedures = new Counter();
        Counter topics = new Counter();
        Counter modalities = new Counter();
        Counter goals = new Counter();
        int advancedHits = 0;
        int beginnerHits = 0;

        for (SessionTurn turn : turns) {
            String text = ((turn.query() == null ? "" : turn.query()) + " " + (turn.report() == null ? "" : turn.report())).toLowerCase(Locale.ROOT);
            detectProcedure(text).ifPresent(procedures::add);
            detectTopics(text).forEach(topics::add);
            firstMatch(text, MODALITY_KEYWORDS).ifPresent(modalities::add);
            firstMatch(text, GOAL_KEYWORDS).ifPresent(goals::add);
            String level = firstMatch(text, LEVEL_KEYWORDS).orElse(null);
            if ("advanced".equals(level)) {
                advancedHits++;
            } else if ("beginner".equals(level)) {
                beginnerHits++;
            }
        }

        List<String> preferredProcedures = procedures.top(3);
        List<String> preferredTopics = topics.top(4);
        List<String> preferredModalities = modalities.top(3);
        if (preferredModalities.isEmpty()) {
            preferredModalities = List.of("text");
        }
        String learningGoal = goals.top(1).stream().findFirst().orElse("knowledge overview");
        String level = advancedHits > beginnerHits ? "advanced" : "beginner";
        List<String> recentFocus = mergeDistinct(preferredTopics, preferredProcedures).stream().limit(4).toList();
        String role = preferredProcedures.isEmpty() ? "general medical learner" : "hepatobiliary learner";
        String label = userId == null ? "session-" + sessionId : "user-" + userId;

        String summary;
        if (queries.isEmpty()) {
            summary = "Current session does not yet contain enough history to infer a detailed profile.";
        } else {
            summary = String.format(
                    Locale.ROOT,
                    "%s recently focused on %s, with attention on %s. The interaction pattern currently looks %s level, prefers %s material, and most aligns with %s.",
                    label,
                    String.join(", ", preferredProcedures.isEmpty() ? List.of("general hepatobiliary topics") : preferredProcedures),
                    String.join(", ", preferredTopics.isEmpty() ? List.of("disease_background") : preferredTopics),
                    level,
                    String.join(", ", preferredModalities),
                    learningGoal
            );
        }

        return new ProfileAnalyzeResponse(
                sessionId,
                label,
                role,
                level,
                preferredProcedures,
                preferredTopics,
                preferredModalities,
                learningGoal,
                recentFocus,
                queries.stream().skip(Math.max(0, queries.size() - 5L)).toList(),
                summary
        );
    }

    private java.util.Optional<String> detectProcedure(String text) {
        for (String candidate : PROCEDURE_KEYWORDS) {
            if (text.contains(candidate)) {
                return java.util.Optional.of(candidate);
            }
        }
        return java.util.Optional.empty();
    }

    private List<String> detectTopics(String text) {
        List<String> matches = new ArrayList<>();
        for (Map.Entry<String, List<String>> entry : TOPIC_KEYWORDS.entrySet()) {
            if (entry.getValue().stream().anyMatch(text::contains)) {
                matches.add(entry.getKey());
            }
        }
        if (matches.isEmpty()) {
            matches.add("disease_background");
        }
        return matches;
    }

    private java.util.Optional<String> firstMatch(String text, Map<String, List<String>> keywords) {
        for (Map.Entry<String, List<String>> entry : keywords.entrySet()) {
            if (entry.getValue().stream().anyMatch(keyword -> containsPhrase(text, keyword))) {
                return java.util.Optional.of(entry.getKey());
            }
        }
        return java.util.Optional.empty();
    }

    private boolean containsPhrase(String text, String keyword) {
        if (keyword.indexOf(' ') >= 0) {
            return text.contains(keyword);
        }
        return Pattern.compile("\\b" + Pattern.quote(keyword) + "\\b").matcher(text).find();
    }

    private List<String> mergeDistinct(List<String> first, List<String> second) {
        Set<String> ordered = new LinkedHashSet<>();
        ordered.addAll(first);
        ordered.addAll(second);
        return new ArrayList<>(ordered);
    }

    private record SessionTurn(
            String query,
            String report,
            String imagePath,
            Timestamp createdAt,
            String stage
    ) {}

    private static final class Counter {
        private final Map<String, Integer> counts = new java.util.LinkedHashMap<>();

        void add(String value) {
            counts.put(value, counts.getOrDefault(value, 0) + 1);
        }

        List<String> top(int limit) {
            return counts.entrySet().stream()
                    .sorted((left, right) -> {
                        int byCount = Integer.compare(right.getValue(), left.getValue());
                        return byCount != 0 ? byCount : left.getKey().compareTo(right.getKey());
                    })
                    .limit(limit)
                    .map(Map.Entry::getKey)
                    .collect(Collectors.toList());
        }
    }
}
