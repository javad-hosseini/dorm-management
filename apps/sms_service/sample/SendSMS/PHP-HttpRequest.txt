<?php

$request = new HttpRequest();
$request->setUrl('http://rest.payamak-panel.com/api/SendSMS/SendSMS');
$request->setMethod(HTTP_METH_POST);

$request->setHeaders(array(
  'content-type' => 'application/x-www-form-urlencoded',
  'postman-token' => '3e37c158-2c35-75aa-1ae7-f76d90ebbe8f',
  'cache-control' => 'no-cache'
));

$request->setContentType('application/x-www-form-urlencoded');
$request->setPostFields(array(
  'username' => 'YourUserName',
  'password' => 'YourPassWord',
  'to' => '936...',
  'from' => '1000...',
  'text' => 'TestSMS',
  'isflash' => 'false'
));

try {
  $response = $request->send();

  echo $response->getBody();
} catch (HttpException $ex) {
  echo $ex;
}