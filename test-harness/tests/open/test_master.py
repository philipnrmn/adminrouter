# -*- coding: utf-8 -*-
# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import logging
import requests

from mocker.endpoints.open.iam import IamEndpoint
from util import verify_header, LineBufferFilter

log = logging.getLogger(__name__)


class TestExhibitorEndpointOpen():
    def test_if_request_is_sent_to_correct_upstream(self,
                                                    master_ar_process,
                                                    valid_user_header):
        url = master_ar_process.make_url_from_path('/exhibitor/some/path')
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=valid_user_header)

        assert resp.status_code == 200
        req_data = resp.json()
        assert req_data['endpoint_id'] == 'http://127.0.0.1:8181'

    def test_if_unknown_user_is_forbidden_access(self,
                                                 master_ar_process,
                                                 invalid_user_header):
        url = master_ar_process.make_url_from_path('/exhibitor/some/path')
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=invalid_user_header)

        assert resp.status_code == 401

    def test_if_valid_user_is_permitted_access(self,
                                               master_ar_process,
                                               valid_user_header):
        url = master_ar_process.make_url_from_path('/exhibitor/some/path')
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=valid_user_header)

        assert resp.status_code == 200

    def test_if_upstream_request_is_correct(self,
                                            master_ar_process,
                                            valid_user_header):
        url = master_ar_process.make_url_from_path('/exhibitor/some/path')
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=valid_user_header)

        assert resp.status_code == 200
        req_data = resp.json()
        assert req_data['method'] == 'GET'
        assert req_data['path'] == '/some/path'
        assert req_data['request_version'] == 'HTTP/1.0'
        verify_header(req_data['headers'], 'X-Forwarded-For', '127.0.0.1')
        verify_header(req_data['headers'], 'X-Forwarded-Proto', 'http')
        verify_header(req_data['headers'], 'X-Real-IP', '127.0.0.1')


class TestAuthenticationOpen():
    def test_if_adding_user_grants_access(
            self, valid_jwt_generator, mocker, master_ar_process):
        uid = 'random_user'

        token = valid_jwt_generator(uid)
        header = {'Authorization': 'token={}'.format(token)}

        url = master_ar_process.make_url_from_path()
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=header)

        assert resp.status_code == 401

        mocker.send_command(endpoint_id='http://127.0.0.1:8101',
                            func_name='add_user',
                            aux_data={'uid': uid})

        resp = requests.get(url,
                            allow_redirects=False,
                            headers=header)

        assert resp.status_code == 200

    def test_if_removing_user_revokes_access(
            self, valid_jwt_generator, mocker, master_ar_process):
        uid = IamEndpoint.users[0]

        token = valid_jwt_generator(uid)
        header = {'Authorization': 'token={}'.format(token)}

        url = master_ar_process.make_url_from_path()
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=header)

        assert resp.status_code == 200

        mocker.send_command(endpoint_id='http://127.0.0.1:8101',
                            func_name='del_user',
                            aux_data={'uid': uid})

        url = master_ar_process.make_url_from_path()
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=header)

        assert resp.status_code == 401

    def test_if_request_sent_to_iam_is_correct(
            self, valid_user_header, mocker, master_ar_process):
        mocker.send_command(endpoint_id='http://127.0.0.1:8101',
                            func_name='record_requests')

        url = master_ar_process.make_url_from_path()
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=valid_user_header)

        assert resp.status_code == 200

        upstream_requests = mocker.send_command(endpoint_id='http://127.0.0.1:8101',
                                                func_name='get_recorded_requests')

        assert len(upstream_requests) == 1

        upstream_request = upstream_requests[0]
        assert upstream_request['path'] == '/acs/api/v1/users/bozydar'
        assert upstream_request['method'] == 'GET'
        assert upstream_request['request_version'] == 'HTTP/1.0'

    def test_if_valid_auth_attempt_is_logged_correctly(
            self, master_ar_process, valid_jwt_generator, mocker):
        # Create some random, unique user that we can grep for:
        uid = 'some_random_string_abc213421341'
        mocker.send_command(endpoint_id='http://127.0.0.1:8101',
                            func_name='add_user',
                            aux_data={'uid': uid})

        filter_string = 'validate_jwt_or_exit(): UID from valid JWT: `{}`'.format(uid)
        lbf = LineBufferFilter(filter_string,
                               line_buffer=master_ar_process.stderr_line_buffer)

        # Create token for this user:
        token = valid_jwt_generator(uid)
        header = {'Authorization': 'token={}'.format(token)}
        url = master_ar_process.make_url_from_path()

        with lbf:
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=header)

        assert resp.status_code == 200
        assert lbf.log_line_found

    def test_if_invalid_auth_attempt_is_logged_correctly(
            self, master_ar_process, valid_jwt_generator):
        # Create some random, unique user that we can grep for:
        uid = 'some_random_string_abc1251231143'

        filter_string = 'validate_jwt_or_exit(): User not found: `{}`'.format(uid)
        lbf = LineBufferFilter(filter_string,
                               line_buffer=master_ar_process.stderr_line_buffer)

        # Create token for this user:
        token = valid_jwt_generator(uid)
        header = {'Authorization': 'token={}'.format(token)}
        url = master_ar_process.make_url_from_path()

        with lbf:
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=header)

        assert resp.status_code == 401
        assert lbf.log_line_found
