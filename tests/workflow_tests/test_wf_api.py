########
# Copyright (c) 2013 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.
import uuid

from cloudify_rest_client.executions import Execution
from testenv import TestCase
from testenv.utils import get_resource as resource
from testenv.utils import deploy_and_execute_workflow as deploy
from testenv.utils import delete_provider_context
from testenv.utils import restore_provider_context


class WorkflowsAPITest(TestCase):

    def setUp(self):
        super(WorkflowsAPITest, self).setUp()
        self.do_get = True
        self.configure(retries=2, interval=1)
        self.addCleanup(restore_provider_context)

    def configure(self, retries, interval):
        delete_provider_context()
        context = {'cloudify': {'workflows': {
            'task_retries': retries,
            'task_retry_interval': interval
        }}}
        self.client.manager.create_context(self._testMethodName, context)

    def test_simple(self):
        parameters = {
            'do_get': self.do_get,
            'key': 'key1',
            'value': 'value1'
        }
        result_dict = {
            'key1': 'value1'
        }
        deployment, _ = deploy(resource('dsl/workflow_api.yaml'),
                               self._testMethodName,
                               parameters=parameters)

        # testing workflow remote task
        invocation = self.get_plugin_data(
            plugin_name='testmockoperations',
            deployment_id=deployment.id
        )['mock_operation_invocation'][0]
        self.assertDictEqual(result_dict, invocation)

        # testing workflow local task
        instance = self.client.node_instances.list(
            deployment_id=deployment.id)[0]
        # I am in love with eventual consistency
        instance = self.client.node_instances.get(instance.id)
        self.assertEqual('test_state', instance.state)
        self.assertDictEqual(result_dict, instance.runtime_properties)

    def test_fail_remote_task_eventual_success(self):
        deployment, _ = deploy(resource('dsl/workflow_api.yaml'), self._testMethodName,
                               parameters={'do_get': self.do_get})

        # testing workflow remote task
        invocations = self.get_plugin_data(
            plugin_name='testmockoperations',
            deployment_id=deployment.id
        )['failure_invocation']
        self.assertEqual(3, len(invocations))
        for i in range(len(invocations) - 1):
            self.assertLessEqual(1, invocations[i+1] - invocations[i])

    def test_fail_remote_task_eventual_failure(self):
        deployment_id = str(uuid.uuid4())
        self.assertRaises(RuntimeError, deploy,
                          resource('dsl/workflow_api.yaml'),
                          self._testMethodName,
                          deployment_id=deployment_id,
                          parameters={'do_get': self.do_get})

        # testing workflow remote task
        invocations = self.get_plugin_data(
            plugin_name='testmockoperations',
            deployment_id=deployment_id
        )['failure_invocation']
        self.assertEqual(3, len(invocations))
        for i in range(len(invocations) - 1):
            self.assertLessEqual(1, invocations[i+1] - invocations[i])

    def test_fail_local_task_eventual_success(self):
        deploy(resource('dsl/workflow_api.yaml'), self._testMethodName,
               parameters={'do_get': self.do_get})

    def test_fail_local_task_eventual_failure(self):
        self._local_task_fail_impl(self._testMethodName)

    def test_fail_local_task_on_nonrecoverable_error(self):
        if not self.do_get:
            # setting infinite retries to make sure that the runtime error
            # raised is not because we ran out of retries
            # (no need to do this when self.do_get because the workflow will
            #  ensure that only one try was attempted)
            self.configure(retries=-1, interval=1)
        self._local_task_fail_impl(self._testMethodName)

    def _local_task_fail_impl(self, wf_name):
        if self.do_get:
            deploy(resource('dsl/workflow_api.yaml'), wf_name,
                   parameters={'do_get': self.do_get})
        else:
            self.assertRaises(RuntimeError,
                              deploy,
                              resource('dsl/workflow_api.yaml'),
                              wf_name,
                              parameters={'do_get': self.do_get})

    def test_cancel_on_wait_for_task_termination(self):
        _, eid = deploy(
            resource('dsl/workflow_api.yaml'), self._testMethodName,
            parameters={'do_get': self.do_get}, wait_for_execution=False)
        self.wait_for_execution_status(eid, status=Execution.STARTED)
        self.client.executions.cancel(eid)
        self.wait_for_execution_status(eid, status=Execution.CANCELLED)

    def test_cancel_on_task_retry_interval(self):
        self.configure(retries=2, interval=1000000)
        _, eid = deploy(
            resource('dsl/workflow_api.yaml'), self._testMethodName,
            parameters={'do_get': self.do_get}, wait_for_execution=False)
        self.wait_for_execution_status(eid, status=Execution.STARTED)
        self.client.executions.cancel(eid)
        self.wait_for_execution_status(eid, status=Execution.CANCELLED)

    def test_illegal_non_graph_to_graph_mode(self):
        if not self.do_get:
            # no need to run twice
            return
        self.assertRaises(RuntimeError, deploy,
                          resource('dsl/workflow_api.yaml'),
                          self._testMethodName)

    def wait_for_execution_status(self, execution_id, status, timeout=30):
        def assertion():
            self.assertEqual(status,
                             self.client.executions.get(execution_id).status)
        self.do_assertions(assertion, timeout=timeout)


class WorkflowsAPITestNoGet(WorkflowsAPITest):

    def setUp(self):
        super(WorkflowsAPITestNoGet, self).setUp()
        self.do_get = False
