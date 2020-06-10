import pytest

from jupyterhub import orm
from tornado.web import MissingArgumentError

from illumidesk.authenticators.handlers import LTI13LoginHandler, LTI13CallbackHandler
from illumidesk.authenticators.authenticator import LTI13Authenticator

from tests.illumidesk.mocks import mock_handler
from tests.illumidesk.factory import factory_auth_state_dict

from oauthenticator.oauth2 import OAuthCallbackHandler

from unittest import mock, IsolatedAsyncioTestCase
from unittest.mock import patch

@pytest.mark.asyncio
async def test_lti_13_login_handler_no_args_body_raises_missing_argument_error():
    """
    Does the LTI13LoginHandler raise a missing argument error if request body doesn't have any
    arguments?
    """
    local_authenticator = LTI13Authenticator()
    local_handler = mock_handler(LTI13LoginHandler, authenticator=local_authenticator)

    with pytest.raises(MissingArgumentError):
        await LTI13LoginHandler(local_handler.application, local_handler.request).post()


class PatchMixin:

    def patch(self, target, **kwargs):
        p = mock.patch(target, **kwargs)
        patch_obj = p.start()
        self.addCleanup(p.stop)
        return patch_obj

class TestLTICallbackHandler(IsolatedAsyncioTestCase, PatchMixin):

    def setUp(self):
        self.mock_check_state = self.patch('oauthenticator.oauth2.OAuthCallbackHandler.check_state')
        self.mock_get_next_url = self.patch('oauthenticator.oauth2.OAuthCallbackHandler.get_next_url')
        self.mock_redirect = self.patch('jupyterhub.handlers.base.BaseHandler.redirect')
        self.mock_login_user = self.patch('jupyterhub.handlers.base.BaseHandler.login_user')
        self.mock_login_user.return_value = orm.User(name='user1')

    async def test_LTI13CallbackHandler_post_method_calls_check_state(self):
        request_handler = mock_handler(OAuthCallbackHandler)
        callback_handler = LTI13CallbackHandler(request_handler.application, request_handler.request)

        await callback_handler.post()
        assert self.mock_check_state.called
    
    async def test_LTI13CallbackHandler_post_method_calls_login_user(self):
        request_handler = mock_handler(OAuthCallbackHandler)
        callback_handler = LTI13CallbackHandler(request_handler.application, request_handler.request)

        await callback_handler.post()
        assert self.mock_login_user.called
    
    async def test_LTI13CallbackHandler_post_method_calls_get_next_url(self):
        request_handler = mock_handler(OAuthCallbackHandler)
        callback_handler = LTI13CallbackHandler(request_handler.application, request_handler.request)

        await callback_handler.post()
        assert self.mock_get_next_url.called

    async def test_LTI13CallbackHandler_post_method_calls_redirect(self):
        request_handler = mock_handler(OAuthCallbackHandler)
        callback_handler = LTI13CallbackHandler(request_handler.application, request_handler.request)

        await callback_handler.post()
        assert self.mock_redirect.called