"""Tests for Resend email backend."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path

from src.messaging.resend_backend import (
    html_to_text,
    load_template,
    render_template,
    init_resend,
    send_resend_email,
    create_magic_link_email_html,
    create_overdue_notification_email_html,
    create_trip_created_email_html,
    create_trip_starting_now_email_html,
    create_checkin_update_email_html,
    create_trip_extended_email_html,
    create_trip_completed_email_html,
    create_overdue_resolved_email_html,
    build_start_location_section,
)


class TestHtmlToText:
    """Tests for HTML to plain text conversion."""

    def test_removes_style_tags(self):
        """Test that style tags and content are removed."""
        html = "<html><style>body { color: red; }</style><body>Hello</body></html>"
        text = html_to_text(html)
        assert "color" not in text
        assert "Hello" in text

    def test_removes_script_tags(self):
        """Test that script tags and content are removed."""
        html = "<html><script>alert('test');</script><body>Hello</body></html>"
        text = html_to_text(html)
        assert "alert" not in text
        assert "Hello" in text

    def test_converts_br_to_newline(self):
        """Test that <br> tags become newlines."""
        html = "Line 1<br>Line 2<br/>Line 3"
        text = html_to_text(html)
        assert "Line 1\nLine 2\nLine 3" in text

    def test_converts_paragraphs(self):
        """Test that </p> adds double newlines."""
        html = "<p>Paragraph 1</p><p>Paragraph 2</p>"
        text = html_to_text(html)
        assert "Paragraph 1\n\nParagraph 2" in text

    def test_converts_list_items_to_bullets(self):
        """Test that list items become bullet points."""
        html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
        text = html_to_text(html)
        assert "• Item 1" in text
        assert "• Item 2" in text

    def test_converts_headings(self):
        """Test that headings add newlines."""
        html = "<h1>Title</h1><p>Content</p>"
        text = html_to_text(html)
        assert "Title\n\nContent" in text

    def test_decodes_html_entities(self):
        """Test that HTML entities are decoded."""
        html = "Tom &amp; Jerry &lt;3 &gt; others &quot;always&quot; don&#39;t"
        text = html_to_text(html)
        assert "Tom & Jerry" in text
        assert "<3" in text
        assert '>' in text
        assert '"always"' in text
        assert "don't" in text

    def test_converts_nbsp(self):
        """Test that &nbsp; becomes space."""
        html = "Hello&nbsp;World"
        text = html_to_text(html)
        assert "Hello World" in text

    def test_removes_remaining_tags(self):
        """Test that all HTML tags are stripped."""
        html = "<div><span class='test'>Hello</span></div>"
        text = html_to_text(html)
        assert "<" not in text
        assert ">" not in text
        assert "Hello" in text

    def test_cleans_whitespace(self):
        """Test that excess whitespace is cleaned."""
        html = "Hello    World   \n\n\n\n  Test"
        text = html_to_text(html)
        assert "Hello World" in text
        # Max 2 consecutive newlines
        assert "\n\n\n" not in text

    def test_strips_result(self):
        """Test that result is stripped of leading/trailing whitespace."""
        html = "   <p>Content</p>   "
        text = html_to_text(html)
        assert not text.startswith(" ")
        assert not text.endswith(" ")


class TestLoadTemplate:
    """Tests for template loading."""

    def test_load_existing_template(self):
        """Test loading an existing email template."""
        # Magic link template should exist
        try:
            template = load_template("magic_link")
            assert isinstance(template, str)
            assert len(template) > 0
        except FileNotFoundError:
            pytest.skip("Template file not found - templates may not be set up")

    def test_load_nonexistent_template(self):
        """Test that loading a nonexistent template raises error."""
        with pytest.raises(FileNotFoundError):
            load_template("nonexistent_template_12345")


class TestRenderTemplate:
    """Tests for template rendering."""

    def test_render_with_variables(self):
        """Test that variables are replaced in template."""
        with patch("src.messaging.resend_backend.load_template") as mock_load:
            mock_load.return_value = "Hello {user_name}, your code is {code}"

            result = render_template("test", user_name="John", code="123456")

            assert result == "Hello John, your code is 123456"

    def test_render_preserves_css_braces(self):
        """Test that CSS curly braces are not affected."""
        with patch("src.messaging.resend_backend.load_template") as mock_load:
            mock_load.return_value = "body { color: red; } Hello {user_name}"

            result = render_template("test", user_name="John")

            # CSS braces should remain intact
            assert "body { color: red; }" in result
            assert "Hello John" in result


class TestBuildStartLocationSection:
    """Tests for building location section HTML."""

    def test_with_start_and_destination(self):
        """Test when both start location and destination are provided."""
        result = build_start_location_section("Home", "Mountain Trail")
        assert "Starting from:" in result
        assert "Home" in result
        assert "Destination:" in result
        assert "Mountain Trail" in result

    def test_with_destination_only(self):
        """Test when only destination is provided."""
        result = build_start_location_section(None, "Mountain Trail")
        assert "Location:" in result
        assert "Mountain Trail" in result
        assert "Starting from:" not in result

    def test_with_no_destination(self):
        """Test when destination is None."""
        result = build_start_location_section(None, None)
        assert "Not specified" in result


class TestInitResend:
    """Tests for Resend initialization."""

    def test_init_without_api_key(self):
        """Test initialization fails gracefully without API key."""
        with patch("src.messaging.resend_backend.settings") as mock_settings:
            mock_settings.RESEND_API_KEY = None

            # Reset the configured flag
            import src.messaging.resend_backend as backend
            backend.resend_configured = False

            result = init_resend()

            assert result is False

    def test_init_with_api_key(self):
        """Test initialization succeeds with API key."""
        with patch("src.messaging.resend_backend.settings") as mock_settings:
            mock_settings.RESEND_API_KEY = "test-api-key"

            # Reset the configured flag
            import src.messaging.resend_backend as backend
            backend.resend_configured = False

            with patch("src.messaging.resend_backend.resend") as mock_resend:
                result = init_resend()

                assert result is True
                assert mock_resend.api_key == "test-api-key"


class TestSendResendEmail:
    """Tests for sending emails via Resend."""

    @pytest.mark.asyncio
    async def test_send_email_not_initialized(self):
        """Test that email fails when Resend not initialized."""
        with patch("src.messaging.resend_backend.init_resend") as mock_init:
            mock_init.return_value = False

            result = await send_resend_email(
                to_email="test@example.com",
                subject="Test",
                html_body="<p>Test</p>"
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_send_email_no_body(self):
        """Test that email fails without body content."""
        with patch("src.messaging.resend_backend.init_resend") as mock_init:
            mock_init.return_value = True

            result = await send_resend_email(
                to_email="test@example.com",
                subject="Test"
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_send_email_success(self):
        """Test successful email sending."""
        with patch("src.messaging.resend_backend.init_resend") as mock_init:
            mock_init.return_value = True

            with patch("src.messaging.resend_backend.settings") as mock_settings:
                mock_settings.RESEND_FROM_EMAIL = "from@example.com"

                with patch("src.messaging.resend_backend.resend.Emails.send") as mock_send:
                    mock_send.return_value = {"id": "test-email-id"}

                    result = await send_resend_email(
                        to_email="test@example.com",
                        subject="Test Subject",
                        html_body="<p>Test body</p>"
                    )

                    assert result is True
                    mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_email_with_text_body(self):
        """Test sending email with text body only."""
        with patch("src.messaging.resend_backend.init_resend") as mock_init:
            mock_init.return_value = True

            with patch("src.messaging.resend_backend.settings") as mock_settings:
                mock_settings.RESEND_FROM_EMAIL = "from@example.com"

                with patch("src.messaging.resend_backend.resend.Emails.send") as mock_send:
                    mock_send.return_value = {"id": "test-email-id"}

                    result = await send_resend_email(
                        to_email="test@example.com",
                        subject="Test Subject",
                        text_body="Plain text body"
                    )

                    assert result is True

    @pytest.mark.asyncio
    async def test_send_email_to_multiple_recipients(self):
        """Test sending email to multiple recipients."""
        with patch("src.messaging.resend_backend.init_resend") as mock_init:
            mock_init.return_value = True

            with patch("src.messaging.resend_backend.settings") as mock_settings:
                mock_settings.RESEND_FROM_EMAIL = "from@example.com"

                with patch("src.messaging.resend_backend.resend.Emails.send") as mock_send:
                    mock_send.return_value = {"id": "test-email-id"}

                    result = await send_resend_email(
                        to_email=["user1@example.com", "user2@example.com"],
                        subject="Test Subject",
                        html_body="<p>Test</p>"
                    )

                    assert result is True

    @pytest.mark.asyncio
    async def test_send_email_high_priority(self):
        """Test sending high priority email."""
        with patch("src.messaging.resend_backend.init_resend") as mock_init:
            mock_init.return_value = True

            with patch("src.messaging.resend_backend.settings") as mock_settings:
                mock_settings.RESEND_FROM_EMAIL = "from@example.com"

                with patch("src.messaging.resend_backend.resend.Emails.send") as mock_send:
                    mock_send.return_value = {"id": "test-email-id"}

                    result = await send_resend_email(
                        to_email="test@example.com",
                        subject="Urgent",
                        html_body="<p>Urgent message</p>",
                        high_priority=True
                    )

                    assert result is True
                    # Verify priority headers were included
                    call_args = mock_send.call_args[0][0]
                    assert "headers" in call_args
                    assert call_args["headers"]["X-Priority"] == "1"

    @pytest.mark.asyncio
    async def test_send_email_with_reply_to(self):
        """Test sending email with reply-to address."""
        with patch("src.messaging.resend_backend.init_resend") as mock_init:
            mock_init.return_value = True

            with patch("src.messaging.resend_backend.settings") as mock_settings:
                mock_settings.RESEND_FROM_EMAIL = "from@example.com"

                with patch("src.messaging.resend_backend.resend.Emails.send") as mock_send:
                    mock_send.return_value = {"id": "test-email-id"}

                    result = await send_resend_email(
                        to_email="test@example.com",
                        subject="Test",
                        html_body="<p>Test</p>",
                        reply_to="reply@example.com"
                    )

                    assert result is True
                    call_args = mock_send.call_args[0][0]
                    assert call_args["reply_to"] == "reply@example.com"

    @pytest.mark.asyncio
    async def test_send_email_error_handling(self):
        """Test that send errors are handled gracefully."""
        with patch("src.messaging.resend_backend.init_resend") as mock_init:
            mock_init.return_value = True

            with patch("src.messaging.resend_backend.settings") as mock_settings:
                mock_settings.RESEND_FROM_EMAIL = "from@example.com"

                with patch("src.messaging.resend_backend.resend.Emails.send") as mock_send:
                    mock_send.side_effect = Exception("API Error")

                    result = await send_resend_email(
                        to_email="test@example.com",
                        subject="Test",
                        html_body="<p>Test</p>"
                    )

                    assert result is False


class TestEmailTemplateCreators:
    """Tests for email template creator functions."""

    def test_create_magic_link_email(self):
        """Test creating magic link email."""
        with patch("src.messaging.resend_backend.render_template") as mock_render:
            mock_render.return_value = "<html>Test</html>"

            result = create_magic_link_email_html("user@example.com", "123456")

            mock_render.assert_called_once_with("magic_link", code="123456", email="user@example.com")
            assert result == "<html>Test</html>"

    def test_create_overdue_notification_email(self):
        """Test creating overdue notification email."""
        with patch("src.messaging.resend_backend.render_template") as mock_render:
            mock_render.return_value = "<html>Overdue</html>"

            result = create_overdue_notification_email_html(
                user_name="John",
                plan_title="Hiking Trip",
                activity="Hiking",
                start_time="10:00 AM",
                expected_time="2:00 PM",
                location="Mountain Trail",
                notes="Be careful"
            )

            assert result == "<html>Overdue</html>"
            mock_render.assert_called_once()

    def test_create_overdue_email_without_notes(self):
        """Test creating overdue email without notes."""
        with patch("src.messaging.resend_backend.render_template") as mock_render:
            mock_render.return_value = "<html>Overdue</html>"

            create_overdue_notification_email_html(
                user_name="John",
                plan_title="Hiking Trip",
                activity="Hiking",
                start_time="10:00 AM",
                expected_time="2:00 PM"
            )

            # Notes should default to "None"
            call_kwargs = mock_render.call_args[1]
            assert call_kwargs["notes"] == "None"

    def test_create_trip_created_email(self):
        """Test creating trip created email."""
        with patch("src.messaging.resend_backend.render_template") as mock_render:
            mock_render.return_value = "<html>Trip Created</html>"

            result = create_trip_created_email_html(
                user_name="John",
                plan_title="Hiking Trip",
                activity="Hiking",
                start_time="10:00 AM",
                expected_time="2:00 PM",
                location="Trail Head"
            )

            assert result == "<html>Trip Created</html>"

    def test_create_trip_starting_now_email(self):
        """Test creating trip starting now email."""
        with patch("src.messaging.resend_backend.render_template") as mock_render:
            mock_render.return_value = "<html>Starting Now</html>"

            result = create_trip_starting_now_email_html(
                user_name="John",
                plan_title="Hiking Trip",
                activity="Hiking",
                expected_time="2:00 PM"
            )

            assert result == "<html>Starting Now</html>"

    def test_create_checkin_update_email(self):
        """Test creating check-in update email."""
        with patch("src.messaging.resend_backend.render_template") as mock_render:
            mock_render.return_value = "<html>Check-in</html>"

            result = create_checkin_update_email_html(
                user_name="John",
                plan_title="Hiking Trip",
                activity="Hiking",
                checkin_time="1:00 PM",
                expected_time="2:00 PM",
                coordinates="37.7749, -122.4194",
                location="Mountain Trail"
            )

            assert result == "<html>Check-in</html>"

    def test_create_trip_extended_email(self):
        """Test creating trip extended email."""
        with patch("src.messaging.resend_backend.render_template") as mock_render:
            mock_render.return_value = "<html>Extended</html>"

            result = create_trip_extended_email_html(
                user_name="John",
                plan_title="Hiking Trip",
                activity="Hiking",
                extended_by=30,
                new_eta="3:00 PM"
            )

            assert result == "<html>Extended</html>"

    def test_create_trip_completed_email(self):
        """Test creating trip completed email."""
        with patch("src.messaging.resend_backend.render_template") as mock_render:
            mock_render.return_value = "<html>Completed</html>"

            result = create_trip_completed_email_html(
                user_name="John",
                plan_title="Hiking Trip",
                activity="Hiking"
            )

            assert result == "<html>Completed</html>"

    def test_create_overdue_resolved_email(self):
        """Test creating overdue resolved email."""
        with patch("src.messaging.resend_backend.render_template") as mock_render:
            mock_render.return_value = "<html>Resolved</html>"

            result = create_overdue_resolved_email_html(
                user_name="John",
                plan_title="Hiking Trip",
                activity="Hiking"
            )

            assert result == "<html>Resolved</html>"
