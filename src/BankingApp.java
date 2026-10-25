package org.example;

import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Scanner;

public class BankingApp {

    private static final String URL =
            "jdbc:postgresql://localhost:5432/deadlock_db";

    private static final String DB_USER = "postgres";
    private static final String DB_PASSWORD = "0int main";

    private static final Scanner scanner = new Scanner(System.in);

    public static void main(String[] args) {
        try (Connection connection = DriverManager.getConnection(
                URL, DB_USER, DB_PASSWORD)) {

            System.out.println("=== Welcome to Banking System ===");

            System.out.print("Enter account ID: ");
            String accountId = scanner.nextLine().trim().toUpperCase();

            System.out.print("Enter PIN: ");
            String pin = scanner.nextLine();

            if (!authenticate(connection, accountId, pin)) {
                System.out.println("Invalid account ID or PIN.");
                return;
            }

            System.out.println("\nLogin successful!");

            while (true) {
                System.out.println("\n===== BANKING MENU =====");
                System.out.println("1. View Balance");
                System.out.println("2. Deposit");
                System.out.println("3. Withdraw");
                System.out.println("4. Exit");
                System.out.print("Choose an option: ");

                String choice = scanner.nextLine().trim();

                try {
                    switch (choice) {
                        case "1" ->
                                viewBalance(connection, accountId);
                        case "2" ->
                                deposit(connection, accountId);
                        case "3" ->
                                withdraw(connection, accountId);
                        case "4" -> {
                            System.out.println("Thank you for banking with us.");
                            return;
                        }
                        default ->
                                System.out.println("Invalid option.");
                    }
                } catch (SQLException e) {
                    System.out.println("Transaction failed: "
                            + e.getMessage());
                } catch (IllegalArgumentException e) {
                    System.out.println(e.getMessage());
                }
            }

        } catch (SQLException e) {
            System.err.println("Database connection failed.");
            System.err.println("Details: " + e.getMessage());
        }
    }

    private static boolean authenticate(
            Connection connection, String accountId, String pin)
            throws SQLException {

        int pinNumber;

        try {
            pinNumber = Integer.parseInt(pin);
        } catch (NumberFormatException e) {
            return false;
        }

        String sql = """
            SELECT 1
            FROM account_credentials
            WHERE account_id = ? AND pin = ?
            """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setString(1, accountId);
            statement.setInt(2, pinNumber);

            try (ResultSet result = statement.executeQuery()) {
                return result.next();
            }
        }
    }

    private static void viewBalance(
            Connection connection, String accountId)
            throws SQLException {

        String sql = """
                SELECT balance
                FROM accounts
                WHERE account_id = ?
                """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setString(1, accountId);

            try (ResultSet result = statement.executeQuery()) {
                if (result.next()) {
                    System.out.println("Current balance: ₹"
                            + result.getBigDecimal("balance"));
                } else {
                    System.out.println("Account not found.");
                }
            }
        }
    }

    private static void deposit(
            Connection connection, String accountId)
            throws SQLException {

        BigDecimal amount = readAmount("Enter deposit amount: ");

        String sql = """
                UPDATE accounts
                SET balance = balance + ?
                WHERE account_id = ?
                """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setBigDecimal(1, amount);
            statement.setString(2, accountId);

            if (statement.executeUpdate() == 1) {
                System.out.println("Deposit successful.");
                viewBalance(connection, accountId);
            } else {
                System.out.println("Account not found.");
            }
        }
    }

    private static void withdraw(
            Connection connection, String accountId)
            throws SQLException {

        BigDecimal amount = readAmount("Enter withdrawal amount: ");

        String sql = """
                UPDATE accounts
                SET balance = balance - ?
                WHERE account_id = ?
                  AND balance >= ?
                """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setBigDecimal(1, amount);
            statement.setString(2, accountId);
            statement.setBigDecimal(3, amount);

            if (statement.executeUpdate() == 1) {
                System.out.println("Withdrawal successful.");
                viewBalance(connection, accountId);
            } else {
                System.out.println(
                        "Insufficient balance or account not found.");
            }
        }
    }

    private static BigDecimal readAmount(String prompt) {
        System.out.print(prompt);
        String input = scanner.nextLine().trim();

        BigDecimal amount;

        try {
            amount = new BigDecimal(input);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException(
                    "Please enter a valid numeric amount.");
        }

        if (amount.compareTo(BigDecimal.ZERO) <= 0) {
            throw new IllegalArgumentException(
                    "Amount must be greater than zero.");
        }

        if (amount.scale() > 2) {
            throw new IllegalArgumentException(
                    "Amount cannot have more than two decimal places.");
        }

        return amount;
    }
}
